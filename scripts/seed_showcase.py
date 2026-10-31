"""Synthetic, repeatable product data for screenshots. No private repository data."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib

from app.db.models import ActionDraft, Issue, KnowledgeSourceDocument, PRFile, PRReviewComment, PullRequest, Repository, WorkflowRun
from app.db.session import SessionLocal
from app.services.rag.indexing import index_repository_documents
from app.services.rag.knowledge_base import get_or_create_config
from app.services.rag.document_processing import process_knowledge_document


def seed_knowledge(repo_id):
    root = Path(__file__).resolve().parents[1]
    data = (root / "docs/datas/evals/codepilot_baseline.md").read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    with SessionLocal() as db:
        source = db.query(KnowledgeSourceDocument).filter_by(repo_id=repo_id, checksum=checksum).first()
        if source is not None and source.status == "completed":
            return
        if source is None:
            stored = root / ".data/docs-preview/codepilot_baseline.md"
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(data)
            source = KnowledgeSourceDocument(repo_id=repo_id, name="codepilot_baseline.md", content_type="text/markdown", checksum=checksum, file_size=len(data), stored_path=str(stored), status="queued")
            db.add(source)
            db.commit()
        source_id = source.id
    process_knowledge_document(source_id)


def main():
    with SessionLocal() as db:
        existing = db.query(Repository).filter_by(full_name="showcase/codepilot-demo").first()
        if existing:
            seed_knowledge(existing.id)
            print("Showcase fixtures already exist")
            return
        now = datetime.now(timezone.utc)
        repo = Repository(owner="showcase", name="codepilot-demo", full_name="showcase/codepilot-demo", description="CodePilot 产品展示 · 合成演示数据", provider="github", default_branch="main", sync_status="completed", last_sync_at=now)
        db.add(repo)
        db.flush()
        db.add_all([
            Issue(repo_id=repo.id, number=12, github_issue_id=12001, title="登录令牌过期后返回 500，应改为 401", body="访问令牌过期后，GET /profile 返回 500。预期返回 401 并引导重新登录。验收：新增过期令牌与无令牌测试。", state="open", labels=["bug", "auth", "priority:high"], author="demo-alice", assignees=[], created_at=now),
            Issue(repo_id=repo.id, number=15, github_issue_id=15001, title="为 GitHub 同步增加失败重试与状态提示", body="网络故障时保留已有 PR 文件和评论，返回部分失败状态。", state="open", labels=["enhancement", "backend"], author="demo-bob", assignees=["demo-backend"], created_at=now),
            Issue(repo_id=repo.id, number=18, github_issue_id=18001, title="知识库回答增加引用来源和无答案提示", body="让用户可以回到证据核验结论。资料不足时明确提示，不编造答案。", state="open", labels=["rag", "feature"], author="demo-carol", created_at=now),
        ])
        pr = PullRequest(repo_id=repo.id, number=24, github_pr_id=24001, title="修复认证边界并补充登录回归测试", body="将令牌过期映射为 401，补充权限边界测试。需要关注异常映射与重试行为。", state="open", author="demo-alice", base_branch="main", head_branch="fix/auth-expiry", created_at=now)
        db.add(pr)
        db.flush()
        db.add_all([
            PRFile(pr_id=pr.id, filename="app/auth.py", status="modified", additions=18, deletions=4, patch="@@ -1,2 +1,3 @@\n-except ExpiredToken:\n-    raise HTTPException(500)\n+except ExpiredToken:\n+    raise HTTPException(401, 'Token expired')"),
            PRFile(pr_id=pr.id, filename="tests/test_auth.py", status="added", additions=32, deletions=0, patch="+def test_expired_token_returns_401(client):\n+    assert client.get('/profile', headers=expired_token()).status_code == 401"),
            PRReviewComment(pr_id=pr.id, body="请同时验证签名错误和无令牌请求，避免异常分支返回 500。", path="app/auth.py", line=12, author="demo-reviewer", created_at=now),
            WorkflowRun(repo_id=repo.id, github_run_id=31001, name="Backend · pytest", status="completed", conclusion="failure", jobs=[{"id": 1, "name": "authentication-tests", "status": "completed", "conclusion": "failure", "steps": [{"name": "Run pytest", "conclusion": "failure"}]}], logs_text="FAILED tests/test_auth.py::test_expired_token_returns_401\nAssertionError: expected status_code 401, got 500", created_at=now),
            WorkflowRun(repo_id=repo.id, github_run_id=31002, name="Frontend · typecheck", status="completed", conclusion="success", logs_text="TypeScript check passed", created_at=now),
            ActionDraft(repo_id=repo.id, draft_type="pr_comment", target_type="pull_request", target_id=pr.id, title="PR #24 审查建议（演示草稿）", content="建议补充：过期令牌返回 401、无令牌请求返回 401、签名无效返回 401。CI 当前仍有认证测试失败，修复后再重新评估合并。", risk_level="medium", meta={"pr_number": 24, "source": "synthetic-showcase"}),
        ])
        db.flush()
        index_repository_documents(db, repo.id)
        config = get_or_create_config(db, repo.id, commit=False)
        config.score_threshold_enabled = False
        config.retrieval_method = "hybrid"
        db.commit()
        seed_knowledge(repo.id)
        print(f"Seeded synthetic showcase: {repo.id}")


if __name__ == "__main__":
    main()
