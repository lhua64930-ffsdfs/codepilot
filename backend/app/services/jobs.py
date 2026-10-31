"""Durable, leased, at-least-once jobs for rebuildable read/index operations.

GitHub writes intentionally never enter this queue: an ambiguous external write
must be reconciled by a human, not retried automatically.
"""
import asyncio
import dataclasses
import importlib
import inspect
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import BackgroundJob
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
HANDLERS = {
    "process_knowledge_document": "app.services.rag.document_processing",
    "scan_project_index_by_id": "app.services.project_indexing",
    "sync_repository_code_analysis_by_id": "app.services.code_analysis",
    "sync_repository_by_id": "app.services.repos_sync",
    "_execute_rag_eval_job": "app.api.routes.evaluations",
    "_execute_rescore_job": "app.api.routes.evaluations",
    "execute_ci_reproduction": "app.services.ci_sandbox",
}
LEASE_SECONDS = 120
MAX_ATTEMPTS = 3


def _record_terminal_failure(db, job):
    """Keep the user-visible operation from remaining running after exhaustion."""
    from app.db.models import EvalRun, KnowledgeSourceDocument, ProjectIndexState, Repository
    args = job.payload.get("args") or []
    if not args:
        return
    raw = args[0].get("$uuid") if isinstance(args[0], dict) else args[0]
    target_id = UUID(str(raw))
    if job.kind in {"_execute_rag_eval_job", "_execute_rescore_job"}:
        target = db.get(EvalRun, target_id)
        if target is not None:
            target.result_json = {**(target.result_json or {}), "status": "error", "execution_status": "error", "quality_status": "incomplete", "progress": {"stage": "error", "message": job.error}}
    elif job.kind == "execute_ci_reproduction":
        from app.db.models import AnalysisResult
        target = db.get(AnalysisResult, target_id)
        if target is not None:
            target.result_json = {**target.result_json, "status": "error", "message": job.error or "复现服务异常，请检查任务日志。"}
    elif job.kind == "process_knowledge_document":
        target = db.get(KnowledgeSourceDocument, target_id)
        if target is not None:
            target.status, target.error_message = "failed", job.error
    elif job.kind == "scan_project_index_by_id":
        target = db.query(ProjectIndexState).filter_by(repo_id=target_id).one_or_none()
        if target is not None:
            target.status, target.error_message = "failed", job.error
    elif job.kind == "sync_repository_by_id":
        target = db.get(Repository, target_id)
        if target is not None:
            target.sync_status, target.sync_errors = "failed", [job.error or "Background sync failed"]


def _encode(value):
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if dataclasses.is_dataclass(value):
        return {"$case": dataclasses.asdict(value)}
    if hasattr(value, "model_dump"):
        return {"$sync": value.model_dump(mode="json")}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _decode(value):
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        if "$uuid" in value:
            return UUID(value["$uuid"])
        if "$case" in value:
            from app.services.evals.ragas_runner import RagEvalCase
            return RagEvalCase(**value["$case"])
        if "$sync" in value:
            from app.schemas.repos import RepoSyncRequest
            return RepoSyncRequest(**value["$sync"])
        return {key: _decode(item) for key, item in value.items()}
    return value


def schedule_job(db: Session, background: BackgroundTasks, handler, *args) -> BackgroundJob:
    if handler.__name__ not in HANDLERS:
        raise ValueError("Unregistered job handler")
    job = BackgroundJob(kind=handler.__name__, payload={"args": _encode(list(args))})
    db.add(job)
    db.commit()
    background.add_task(run_job_by_id, job.id)
    return job


def _eligible(now):
    return or_(
        (BackgroundJob.status == "queued") & (BackgroundJob.available_at <= now),
        (BackgroundJob.status == "running") & (BackgroundJob.lease_until < now) & (BackgroundJob.attempts < MAX_ATTEMPTS),
    )


async def _heartbeat(job_id, token):
    while True:
        await asyncio.sleep(LEASE_SECONDS / 3)
        with SessionLocal() as db:
            db.query(BackgroundJob).filter_by(id=job_id, lease_token=token, status="running").update(
                {"lease_until": datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)}, synchronize_session=False,
            )
            db.commit()


async def run_job_by_id(job_id: UUID) -> bool:
    token = uuid4().hex
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        claimed = db.query(BackgroundJob).filter(BackgroundJob.id == job_id, _eligible(now)).update(
            {"status": "running", "lease_token": token, "lease_until": now + timedelta(seconds=LEASE_SECONDS), "attempts": BackgroundJob.attempts + 1},
            synchronize_session=False,
        )
        db.commit()
        if not claimed:
            return False
        job = db.get(BackgroundJob, job_id)
        kind, payload, attempts = job.kind, job.payload, job.attempts
    heartbeat = asyncio.create_task(_heartbeat(job_id, token))
    error = None
    try:
        handler = getattr(importlib.import_module(HANDLERS[kind]), kind)
        args = _decode(payload["args"])
        if inspect.iscoroutinefunction(handler):
            await handler(*args)
        else:
            await asyncio.to_thread(handler, *args)
        if kind == "process_knowledge_document":
            from app.db.models import KnowledgeSourceDocument
            with SessionLocal() as db:
                document = db.get(KnowledgeSourceDocument, args[0])
                if document is not None and document.status == "failed":
                    raise RuntimeError(document.error_message or "Document processing failed")
    except Exception as exc:
        logger.exception("Background job failed: %s", job_id)
        error = f"{type(exc).__name__}: {exc}"
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat
    with SessionLocal() as db:
        db.query(BackgroundJob).filter_by(id=job_id, lease_token=token).update({
            "status": "completed" if error is None else ("queued" if attempts < MAX_ATTEMPTS else "failed"),
            "error": error, "lease_token": None, "lease_until": None,
            "available_at": datetime.now(timezone.utc) + timedelta(seconds=10 * attempts),
        }, synchronize_session=False)
        terminal = db.get(BackgroundJob, job_id)
        if terminal.status == "failed":
            _record_terminal_failure(db, terminal)
        db.commit()
    return True


async def job_worker_loop():
    while True:
        try:
            with SessionLocal() as db:
                # Repeated process crashes must not produce unlimited retries.
                expired = db.query(BackgroundJob).filter(
                    BackgroundJob.status == "running", BackgroundJob.lease_until < datetime.now(timezone.utc),
                    BackgroundJob.attempts >= MAX_ATTEMPTS,
                ).all()
                for job in expired:
                    job.status = "failed"
                    job.error = "Worker interrupted repeatedly; retry budget exhausted"
                    job.lease_token = None
                    _record_terminal_failure(db, job)
                db.commit()
                ids = list(db.scalars(select(BackgroundJob.id).where(_eligible(datetime.now(timezone.utc))).order_by(BackgroundJob.created_at).limit(10)))
            for job_id in ids:
                await run_job_by_id(job_id)
        except Exception:
            logger.exception("Job worker poll failed")
        await asyncio.sleep(3)
