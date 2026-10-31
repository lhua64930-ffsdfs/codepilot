import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import ActionDraft, BackgroundJob, Base, Document, EvalRun, Issue, PRFile, PRReviewComment, PullRequest, Repository, RepositoryMember, User
from app.db.session import get_db
from app.main import create_app
from app.schemas.repos import RepoSyncRequest
from app.services.authentication import apply_repository_scope, token_hash
from app.services.evals.suites import DEFAULT_SUITE_DIR, load_eval_suite
from app.services.jobs import run_job_by_id, schedule_job
from app.services.rag.retrieval import expand_parent_context
from app.services.repos_sync import sync_repository


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        yield db, factory
    engine.dispose()


def repo(db, name="demo"):
    row = Repository(owner="local", name=name, full_name=f"local/{name}")
    db.add(row)
    db.flush()
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["status", "timeout"])
async def test_sync_failure_preserves_pr_details(database, monkeypatch, failure):
    db, _ = database
    repository = repo(db)
    pr = PullRequest(repo_id=repository.id, github_pr_id=1, number=1, title="PR")
    db.add(pr)
    db.flush()
    db.add_all([PRFile(pr_id=pr.id, filename="keep.py", status="modified"), PRReviewComment(pr_id=pr.id, body="keep comment")])
    db.commit()

    async def prs(*a, **k): return [{"id": 1, "number": 1, "title": "PR"}]
    async def fail(*a, **k):
        if failure == "timeout": raise httpx.ReadTimeout("timeout")
        response = httpx.Response(503, request=httpx.Request("GET", "https://api.github.com"))
        raise httpx.HTTPStatusError("unavailable", request=response.request, response=response)
    monkeypatch.setattr("app.services.repos_sync.list_pull_requests", prs)
    monkeypatch.setattr("app.services.repos_sync.list_pull_request_files", fail)
    monkeypatch.setattr("app.services.repos_sync.list_pull_request_review_comments", fail)
    result = await sync_repository(db, repository, RepoSyncRequest(sync_issues=False, sync_workflow_runs=False))
    assert result.status == "partial" and len(result.errors) == 2
    assert db.query(PRFile).one().filename == "keep.py"
    assert db.query(PRReviewComment).one().body == "keep comment"
    assert repository.last_sync_at is None


@pytest.mark.asyncio
async def test_confirm_claim_prevents_concurrent_external_writes(database, monkeypatch):
    from app.api.routes import action_drafts
    db, factory = database
    repository = repo(db)
    user = User(name="approver", role="owner")
    db.add(user)
    db.flush()
    draft = ActionDraft(repo_id=repository.id, draft_type="create_issue", target_type="repository", content="body")
    db.add(draft)
    db.commit()
    started, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def execute(*args):
        calls.append(1)
        started.set()
        await release.wait()
        return {"id": 123}
    monkeypatch.setattr(action_drafts, "_execute_github_draft", execute)
    with factory() as second:
        stale = second.get(ActionDraft, draft.id)
        assert stale.status == "pending_confirmation"
        first = asyncio.create_task(action_drafts.confirm_action_draft(draft.id, db=db, user=user))
        await started.wait()
        with pytest.raises(HTTPException):
            await action_drafts.confirm_action_draft(draft.id, db=second, user=user)
    release.set()
    result = await first
    assert result["draft"].status == "executed" and calls == [1]


@pytest.mark.asyncio
async def test_ambiguous_write_is_not_retryable(database, monkeypatch):
    from app.api.routes import action_drafts
    db, _ = database
    repository = repo(db)
    user = User(name="owner")
    db.add(user)
    db.flush()
    draft = ActionDraft(repo_id=repository.id, draft_type="create_issue", target_type="repository", content="body")
    db.add(draft)
    db.commit()
    async def timeout(*a): raise httpx.ReadTimeout("unknown result")
    monkeypatch.setattr(action_drafts, "_execute_github_draft", timeout)
    result = await action_drafts.confirm_action_draft(draft.id, db=db, user=user)
    assert result["draft"].status == "unknown"
    with pytest.raises(HTTPException):
        await action_drafts.confirm_action_draft(draft.id, db=db, user=user)


@pytest.mark.asyncio
async def test_api_authentication_permissions_and_repo_isolation(database, monkeypatch):
    db, factory = database
    first, other = repo(db, "first"), repo(db, "other")
    user = User(name="reader", role="viewer", api_token_hash=token_hash("reader-token"))
    db.add(user)
    db.flush()
    db.add(RepositoryMember(user_id=user.id, repo_id=first.id))
    issue = Issue(repo_id=other.id, number=1, title="private")
    db.add(issue)
    db.commit()
    monkeypatch.setattr(settings, "demo_mode", False)
    app = create_app()
    def dependency():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = dependency
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/repos")).status_code == 401
        client.headers["Authorization"] = "Bearer reader-token"
        response = await client.get("/api/repos")
        assert response.status_code == 200 and [r["id"] for r in response.json()] == [str(first.id)]
        assert (await client.get(f"/api/repos/{other.id}/issues")).status_code == 404
        assert (await client.get(f"/api/issues/{issue.id}")).status_code == 404
        assert (await client.post(f"/api/repos/{first.id}/sync", json={})).status_code == 403
        assert (await client.delete(f"/api/repos/{first.id}")).status_code == 403
        client.headers["Authorization"] = "Bearer invalid"
        assert (await client.get("/api/repos")).status_code == 401


def test_tenant_scope_does_not_leak_between_cached_queries(database):
    db, factory = database
    first, other = repo(db, "one"), repo(db, "two")
    users = [User(name="one", role="developer"), User(name="two", role="developer")]
    db.add_all(users)
    db.flush()
    db.add_all([RepositoryMember(user_id=users[0].id, repo_id=first.id), RepositoryMember(user_id=users[1].id, repo_id=other.id)])
    db.commit()
    for user, expected in zip(users, [first, other]):
        with factory() as scoped:
            apply_repository_scope(scoped, user)
            assert [r.id for r in scoped.scalars(select(Repository))] == [expected.id]


@pytest.mark.asyncio
async def test_job_reclaims_expired_lease_once(database, monkeypatch):
    from app.services import jobs
    from app.services import repos_sync
    db, factory = database
    calls = []
    async def handler(*args): calls.append(args)
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    monkeypatch.setattr(repos_sync, "sync_repository_by_id", handler)
    row = BackgroundJob(kind="sync_repository_by_id", payload={"args": []}, status="running", attempts=1, lease_until=datetime.now(timezone.utc) - timedelta(seconds=1))
    db.add(row)
    db.commit()
    assert await run_job_by_id(row.id)
    assert not await run_job_by_id(row.id)
    db.refresh(row)
    assert row.status == "completed" and row.attempts == 2 and len(calls) == 1


@pytest.mark.asyncio
async def test_job_failure_has_bounded_retries(database, monkeypatch):
    from app.services import jobs, repos_sync
    db, factory = database
    async def fail(*args): raise RuntimeError("offline")
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    monkeypatch.setattr(repos_sync, "sync_repository_by_id", fail)
    row = BackgroundJob(kind="sync_repository_by_id", payload={"args": []}, attempts=2)
    db.add(row)
    db.commit()
    await run_job_by_id(row.id)
    db.refresh(row)
    assert row.status == "failed" and "offline" in row.error


def test_parent_expansion_batches_queries_and_preserves_repo_boundary(database):
    db, _ = database
    repository, other = repo(db), repo(db, "other")
    source = uuid.uuid4()
    items = []
    for index in range(3):
        metadata = {"parent_id": "parent", "child_index": index}
        row = Document(repo_id=repository.id, source_type="knowledge_file", source_id=source, title="chunk", content=f"chunk-{index}", meta=metadata)
        db.add(row)
        db.flush()
        items.append({"id": str(row.id), "source_id": str(source), "source_type": "knowledge_file", "metadata": metadata})
    db.add(Document(repo_id=other.id, source_type="knowledge_file", source_id=source, title="secret", content="SECRET", meta={"parent_id": "parent", "child_index": 1}))
    db.commit()
    queries = []
    def count(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("SELECT"): queries.append(statement)
    event.listen(db.bind, "before_cursor_execute", count)
    try:
        expanded, _ = expand_parent_context(db, repository.id, items)
    finally:
        event.remove(db.bind, "before_cursor_execute", count)
    # Loading an expired repository id may add one query; source expansion itself
    # must perform one SELECT regardless of the number of hits.
    assert sum("FROM documents" in query for query in queries) == 1
    assert all("SECRET" not in item["_raw_content"] for item in expanded)


def test_fixed_baseline_is_shipped_and_loadable(database):
    db, _ = database
    repository = repo(db)
    document = Document(repo_id=repository.id, source_type="knowledge_file", source_id=uuid.uuid4(), title="baseline", content="baseline", meta={"filename": "codepilot_baseline.md"})
    db.add(document)
    db.commit()
    suite = load_eval_suite(db, repository.id, "devflow-real-project-rag-baseline")
    assert len(suite.cases) >= 10 and suite.metadata["sha256"]
    assert any(case.required_tools for case in suite.cases)
    assert any(case.kind == "unanswerable" for case in suite.cases)
    assert all(case.reference and case.question for case in suite.cases)
    assert (DEFAULT_SUITE_DIR / "codepilot_baseline.md").is_file()


def test_alembic_adopts_legacy_schema_without_dropping_data(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app.db import session
    from app.db.schema import verify_schema
    engine = create_engine(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY, name VARCHAR(200), github_token_encrypted TEXT, created_at DATETIME)"))
        connection.execute(text("INSERT INTO users (id, name) VALUES (:id, 'legacy-user')"), {"id": uuid.uuid4().hex})
    monkeypatch.setattr(session, "engine", engine)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    verify_schema(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT name FROM users")) == "legacy-user"
        assert connection.scalar(text("SELECT role FROM users")) == "owner"
        assert connection.scalar(text("SELECT COUNT(*) FROM background_jobs")) == 0
    engine.dispose()
