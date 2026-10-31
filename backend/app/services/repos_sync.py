from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_token
from app.db.models import Issue, PRFile, PRReviewComment, PullRequest, Repository, WorkflowRun
from app.schemas.repos import RepoSyncRequest, RepoSyncResponse
from app.services.github.actions import get_workflow_run_logs, list_workflow_run_jobs, list_workflow_runs
from app.services.github.issues import list_issues
from app.services.github.pull_requests import list_pull_request_files, list_pull_request_review_comments, list_pull_requests
from app.services.repo_lock import repository_sync_lock


def parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def login_of(user: dict | None) -> str | None:
    return user.get("login") if user else None


async def sync_repository(db: Session, repo: Repository, payload: RepoSyncRequest) -> RepoSyncResponse:
    async with repository_sync_lock(db, repo.id):
        try:
            return await _sync_repository(db, repo, payload)
        except Exception as exc:
            db.rollback()
            repo.sync_status = "failed"
            repo.sync_errors = [type(exc).__name__]
            db.commit()
            raise


async def _sync_repository(db: Session, repo: Repository, payload: RepoSyncRequest) -> RepoSyncResponse:
    if repo.provider not in {"github", "github_compatible"}:
        raise HTTPException(status_code=400, detail=f"{repo.provider} sync is not implemented yet")

    synced = {"issues": 0, "pull_requests": 0, "workflow_runs": 0}
    errors: list[str] = []
    token = decrypt_token(repo.github_token_encrypted, settings.token_encryption_key) if repo.github_token_encrypted else None
    base_url = repo.api_base_url

    if payload.sync_issues:
        try:
            remote_issues = await list_issues(repo.owner, repo.name, token=token, limit=payload.limit, base_url=base_url)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=400, detail=f"GitHub issues sync failed: {exc.response.status_code} {exc.response.text}") from exc
        for item in remote_issues:
            issue = db.query(Issue).filter(Issue.repo_id == repo.id, Issue.github_issue_id == item.get("id")).one_or_none()
            if issue is None:
                issue = Issue(repo_id=repo.id, github_issue_id=item.get("id"), number=item.get("number", 0), title=item.get("title") or "")
                db.add(issue)
            issue.number = item.get("number", issue.number)
            issue.title = item.get("title") or issue.title
            issue.body = item.get("body")
            issue.state = item.get("state") or "open"
            issue.labels = [label.get("name") for label in item.get("labels", []) if label.get("name")]
            issue.author = login_of(item.get("user"))
            issue.assignees = [login_of(user) for user in item.get("assignees", []) if login_of(user)]
            issue.created_at = parse_github_datetime(item.get("created_at"))
            issue.updated_at = parse_github_datetime(item.get("updated_at"))
            issue.closed_at = parse_github_datetime(item.get("closed_at"))
            synced["issues"] += 1

    if payload.sync_pull_requests:
        try:
            remote_prs = await list_pull_requests(repo.owner, repo.name, token=token, limit=payload.limit, base_url=base_url)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=400, detail=f"GitHub pull requests sync failed: {exc.response.status_code} {exc.response.text}") from exc
        for item in remote_prs:
            pr = db.query(PullRequest).filter(PullRequest.repo_id == repo.id, PullRequest.github_pr_id == item.get("id")).one_or_none()
            if pr is None:
                pr = PullRequest(repo_id=repo.id, github_pr_id=item.get("id"), number=item.get("number", 0), title=item.get("title") or "")
                db.add(pr)
                db.flush()
            pr.number = item.get("number", pr.number)
            pr.title = item.get("title") or pr.title
            pr.body = item.get("body")
            pr.state = item.get("state") or "open"
            pr.author = login_of(item.get("user"))
            pr.base_branch = (item.get("base") or {}).get("ref")
            pr.head_branch = (item.get("head") or {}).get("ref")
            pr.merged_at = parse_github_datetime(item.get("merged_at"))
            pr.created_at = parse_github_datetime(item.get("created_at"))
            pr.updated_at = parse_github_datetime(item.get("updated_at"))

            try:
                files = await list_pull_request_files(repo.owner, repo.name, pr.number, token=token, base_url=base_url)
            except httpx.HTTPError as exc:
                files = None
                errors.append(f"PR #{pr.number} files: {type(exc).__name__}")
            if files is not None:
                db.query(PRFile).filter(PRFile.pr_id == pr.id).delete()
            for file_item in files or []:
                db.add(
                    PRFile(
                        pr_id=pr.id,
                        filename=file_item.get("filename") or "",
                        status=file_item.get("status") or "modified",
                        additions=file_item.get("additions") or 0,
                        deletions=file_item.get("deletions") or 0,
                        patch=file_item.get("patch"),
                    )
                )
            try:
                review_comments = await list_pull_request_review_comments(repo.owner, repo.name, pr.number, token=token, base_url=base_url)
            except httpx.HTTPError as exc:
                review_comments = None
                errors.append(f"PR #{pr.number} review comments: {type(exc).__name__}")
            if review_comments is not None:
                db.query(PRReviewComment).filter(PRReviewComment.pr_id == pr.id).delete()
            for comment_item in review_comments or []:
                db.add(
                    PRReviewComment(
                        pr_id=pr.id,
                        github_comment_id=comment_item.get("id"),
                        body=comment_item.get("body"),
                        path=comment_item.get("path"),
                        line=comment_item.get("line") or comment_item.get("original_line"),
                        author=login_of(comment_item.get("user")),
                        created_at=parse_github_datetime(comment_item.get("created_at")),
                        updated_at=parse_github_datetime(comment_item.get("updated_at")),
                    )
                )
            synced["pull_requests"] += 1

    if payload.sync_workflow_runs:
        try:
            remote_runs = await list_workflow_runs(repo.owner, repo.name, token=token, limit=payload.limit, base_url=base_url)
        except httpx.HTTPError as exc:
            remote_runs = []
            errors.append(f"workflow runs: {type(exc).__name__}")
        for item in remote_runs:
            run = db.query(WorkflowRun).filter(WorkflowRun.repo_id == repo.id, WorkflowRun.github_run_id == item.get("id")).one_or_none()
            if run is None:
                run = WorkflowRun(repo_id=repo.id, github_run_id=item.get("id"), name=item.get("name") or "workflow")
                db.add(run)
            run.name = item.get("name") or run.name
            run.status = item.get("status") or "unknown"
            run.conclusion = item.get("conclusion")
            run.html_url = item.get("html_url")
            run.created_at = parse_github_datetime(item.get("created_at"))
            run.updated_at = parse_github_datetime(item.get("updated_at"))
            if run.github_run_id:
                try:
                    jobs = await list_workflow_run_jobs(repo.owner, repo.name, run.github_run_id, token=token, base_url=base_url)
                    run.jobs = [
                        {
                            "id": job.get("id"),
                            "name": job.get("name"),
                            "status": job.get("status"),
                            "conclusion": job.get("conclusion"),
                            "html_url": job.get("html_url"),
                            "started_at": job.get("started_at"),
                            "completed_at": job.get("completed_at"),
                            "steps": [
                                {
                                    "name": step.get("name"),
                                    "status": step.get("status"),
                                    "conclusion": step.get("conclusion"),
                                    "number": step.get("number"),
                                }
                                for step in job.get("steps", [])
                            ],
                        }
                        for job in jobs
                    ]
                except httpx.HTTPError as exc:
                    run.jobs = run.jobs or []
                    errors.append(f"workflow {run.github_run_id} jobs: {type(exc).__name__}")
            if run.conclusion == "failure" and run.github_run_id:
                try:
                    run.logs_text = await get_workflow_run_logs(repo.owner, repo.name, run.github_run_id, token=token, base_url=base_url)
                except httpx.HTTPError as exc:
                    errors.append(f"workflow {run.github_run_id} logs: {type(exc).__name__}")
            synced["workflow_runs"] += 1

    if not errors:
        repo.last_sync_at = datetime.now(timezone.utc)
    repo.sync_status = "partial" if errors else "completed"
    repo.sync_errors = errors
    db.flush()
    db.commit()
    return RepoSyncResponse(repo_id=repo.id, status="partial" if errors else "completed", synced=synced, errors=errors)


async def sync_repository_by_id(repo_id: UUID, payload: RepoSyncRequest) -> RepoSyncResponse | None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        repo = db.get(Repository, repo_id)
        if repo is None:
            return None
        return await sync_repository(db, repo, payload)
    finally:
        db.close()
