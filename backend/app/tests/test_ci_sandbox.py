import io
import os
import subprocess
import tarfile
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import AnalysisResult, AuditLog, BackgroundJob, Base, Repository, RepositoryMember, User, WorkflowRun
from app.db.session import get_db
from app.main import create_app
from app.services import ci_sandbox
from app.services.authentication import token_hash


def git(path, *args):
    return subprocess.check_output(["git", "-c", "user.name=Sandbox Test", "-c", "user.email=sandbox@example.invalid", *args], cwd=path).decode().strip()


def repository(tmp_path, source="def test_example():\n    assert True\n"):
    git(tmp_path, "init", "-q")
    (tmp_path / "test_example.py").write_text(source, encoding="utf-8")
    (tmp_path / ".env").write_text("DO_NOT_COPY=secret", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "fixture")
    return git(tmp_path, "rev-parse", "HEAD")


@pytest.mark.parametrize("directory", ["../outside", "/tmp", "C:/secrets", "foo\\bar", "", "a/../../b"])
def test_rejects_outside_working_directory(directory):
    with pytest.raises(ValueError):
        ci_sandbox.validate_request(["python", "-m", "pytest"], directory)


@pytest.mark.parametrize("command", [["sh", "-c", "whoami"], ["python", "-c", "print(1)"], [], ["docker", "run"], ["python", "-m", "pytest", "bad\x00arg"]])
def test_rejects_unapproved_commands(command):
    with pytest.raises(ValueError):
        ci_sandbox.validate_request(command, ".")


def test_snapshot_uses_commit_excludes_local_secrets_and_links(tmp_path):
    sha = repository(tmp_path)
    (tmp_path / "test_example.py").write_text("CHANGED LIVE CHECKOUT", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("UNTRACKED SECRET", encoding="utf-8")
    data = ci_sandbox.snapshot(tmp_path, sha)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        assert archive.getnames() == ["test_example.py"]
        assert b"assert True" in archive.extractfile("test_example.py").read()
    for name in ["../outside", "/outside", ".aws/credentials", ".ENV.LOCAL", "key.pem", "a/.git/config"]:
        member = tarfile.TarInfo(name)
        assert not ci_sandbox._safe_member(member)
    for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]:
        member = tarfile.TarInfo("link")
        member.type = kind
        assert not ci_sandbox._safe_member(member)


def test_missing_commit_blocks_without_running_repo_code(tmp_path):
    repository(tmp_path)
    with pytest.raises(ValueError):
        ci_sandbox.snapshot(tmp_path, "f" * 40)


def test_archive_size_is_bounded(tmp_path, monkeypatch):
    sha = repository(tmp_path)
    monkeypatch.setattr(ci_sandbox, "MAX_SNAPSHOT", 100)
    with pytest.raises(ValueError):
        ci_sandbox.snapshot(tmp_path, sha)


def test_capture_drains_excess_output_and_times_out():
    import sys
    code, output, timeout, truncated = ci_sandbox._capture(
        [sys.executable, "-c", "print('x' * 200000)"], timeout=5, limit=100)
    assert code == 0 and len(output) == 100 and truncated and not timeout
    _, _, timeout, _ = ci_sandbox._capture([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1, limit=100)
    assert timeout


@pytest.mark.parametrize("exit_code,status", [(0, "passed"), (1, "failed"), (124, "timeout"), (125, "blocked")])
def test_outcomes_cleanup_and_no_host_fallback(monkeypatch, exit_code, status):
    monkeypatch.setattr(settings, "ci_sandbox_enabled", True)
    monkeypatch.setattr(ci_sandbox, "snapshot", lambda *_: b"archive")
    calls = []
    def capture(args, **kwargs):
        calls.append(args)
        return exit_code, b"test output", False, False
    monkeypatch.setattr(ci_sandbox, "_capture", capture)
    result = ci_sandbox.reproduce("unused", "a" * 40, ["python", "-m", "pytest"], ".", str(uuid4()))
    assert result["status"] == status
    assert calls[-1][:3] == ["docker", "rm", "-f"]
    run = next(args for args in calls if args[:2] == ["docker", "run"])
    assert all(flag in run for flag in ["--network=none", "--read-only", "--cap-drop=ALL", "--pids-limit=64", "--pull=never"])
    assert not any("docker.sock" in arg or arg.startswith("--volume") for arg in run)


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        yield db, factory
    engine.dispose()


@pytest.mark.asyncio
async def test_api_authorization_enqueue_history_and_isolation(database, monkeypatch):
    from app.services import jobs
    db, factory = database
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "ci_sandbox_enabled", True)
    repo = Repository(owner="test", name="demo", full_name="test/demo")
    other = Repository(owner="test", name="other", full_name="test/other")
    dev = User(name="dev", role="developer", api_token_hash=token_hash("dev-token"))
    viewer = User(name="viewer", role="viewer", api_token_hash=token_hash("viewer-token"))
    db.add_all([repo, other, dev, viewer])
    db.flush()
    db.add_all([RepositoryMember(repo_id=repo.id, user_id=dev.id), RepositoryMember(repo_id=repo.id, user_id=viewer.id)])
    run = WorkflowRun(repo_id=repo.id, name="pytest", status="completed", conclusion="failure", head_sha="a" * 40)
    hidden = WorkflowRun(repo_id=other.id, name="private", status="completed", conclusion="failure", head_sha="b" * 40)
    db.add_all([run, hidden])
    db.commit()
    run_id, hidden_id = run.id, hidden.id
    async def no_execution(*_): pass
    monkeypatch.setattr(jobs, "run_job_by_id", no_execution)
    app = create_app()
    def dependency():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = dependency
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/workflow-runs/{run_id}/reproductions"
        response = await client.post(path, json={}, headers={"Authorization": "Bearer viewer-token"})
        assert response.status_code == 403
        headers = {"Authorization": "Bearer dev-token"}
        assert (await client.get(f"/api/workflow-runs/{hidden_id}/reproductions", headers=headers)).status_code == 404
        assert (await client.post(f"/api/workflow-runs/{hidden_id}/reproductions", json={}, headers=headers)).status_code == 404
        assert (await client.post(path, json={"command": ["sh", "-c", "echo unsafe"]}, headers=headers)).status_code == 422
        response = await client.post(path, json={}, headers=headers)
        assert response.status_code == 202, response.text
        assert response.json()["result"]["commit_sha"] == "a" * 40
        assert (await client.post(path, json={}, headers=headers)).status_code == 409
        history = await client.get(path, headers=headers)
        assert len(history.json()) == 1
    assert db.query(BackgroundJob).one().kind == "execute_ci_reproduction"
    assert db.query(AuditLog).one().user_id == dev.id


@pytest.mark.asyncio
async def test_agent_preserves_real_evidence_even_if_model_invents_results():
    from app.services.agents.ci_debug_agent import CIDebugAgent
    class FakeLLM:
        async def chat_json(self, *_):
            return {"reproduction": {"status": "passed", "output": "invented"}, "is_merge_blocking": False}
    actual = {"status": "blocked", "message": "missing dependencies", "exit_code": 125}
    result = await CIDebugAgent(llm=FakeLLM()).run(
        {"name": "pytest", "status": "completed", "conclusion": "failure", "logs_text": "AssertionError"},
        {"reproduction": actual})
    assert result["reproduction"] == actual
    assert result["is_merge_blocking"] is True


def test_upgrade_existing_workflow_table_preserves_data(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from sqlalchemy import text, inspect
    from app.db import session
    from app.db.schema import verify_schema
    engine = create_engine(f"sqlite:///{(tmp_path / 'upgrade.db').as_posix()}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE workflow_runs DROP COLUMN head_sha"))
        conn.execute(text("INSERT INTO workflow_runs (id, repo_id, name, status, jobs) VALUES (:id, :repo, 'keep-ci', 'completed', '[]')"),
                     {"id": uuid4().hex, "repo": uuid4().hex})
    monkeypatch.setattr(session, "engine", engine)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.stamp(config, "0001_reliability")
    command.upgrade(config, "head")
    verify_schema(engine)
    with engine.connect() as conn:
        assert "head_sha" in {c["name"] for c in inspect(conn).get_columns("workflow_runs")}
        assert conn.scalar(text("SELECT name FROM workflow_runs")) == "keep-ci"
    engine.dispose()


@pytest.mark.asyncio
async def test_worker_persists_result_and_never_replays_interrupted_task(database, monkeypatch):
    db, factory = database
    monkeypatch.setattr(ci_sandbox, "SessionLocal", factory)
    repo = Repository(owner="t", name="r", full_name="t/r")
    db.add(repo)
    db.flush()
    run = WorkflowRun(repo_id=repo.id, name="test", status="completed", conclusion="failure")
    db.add(run)
    db.flush()
    row = AnalysisResult(target_type="workflow_run", target_id=run.id, analysis_type="ci_reproduction",
        input_snapshot={"command": ["python", "-m", "pytest"], "working_directory": ".", "commit_sha": "a" * 40}, result_json={"status": "queued"})
    db.add(row)
    db.commit()
    calls = []
    def fake(*args):
        calls.append(args)
        return {"status": "failed", "exit_code": 1, "output": "assertion"}
    monkeypatch.setattr(ci_sandbox, "reproduce", fake)
    await ci_sandbox.execute_ci_reproduction(row.id)
    db.refresh(row)
    assert row.result_json["status"] == "failed"
    await ci_sandbox.execute_ci_reproduction(row.id)
    assert len(calls) == 1
    row.result_json = {"status": "running"}
    db.commit()
    monkeypatch.setattr(ci_sandbox, "_capture", lambda *a, **k: (0, b"", False, False))
    await ci_sandbox.execute_ci_reproduction(row.id)
    db.refresh(row)
    assert row.result_json["status"] == "interrupted" and len(calls) == 1


@pytest.mark.skipif(os.environ.get("CODEPILOT_SANDBOX_INTEGRATION") != "1", reason="Requires the locally built Docker sandbox image")
@pytest.mark.parametrize("scenario", ["isolation", "assertion", "timeout", "output"])
def test_real_docker_sandbox(tmp_path, monkeypatch, scenario):
    sources = {
        "isolation": '''import os, pathlib, socket
def test_isolation():
    assert os.getuid() == 10001
    assert not pathlib.Path('.env').exists()
    assert not pathlib.Path('.git').exists()
    assert 'GITHUB_TOKEN' not in os.environ
    assert 'DATABASE_URL' not in os.environ
    try:
        pathlib.Path('/opt/codepilot/changed').write_text('escape')
    except OSError:
        pass
    else:
        assert False, 'root filesystem must be read only'
    with socket.socket() as s:
        s.settimeout(1)
        assert s.connect_ex(('1.1.1.1', 443)) != 0
    pathlib.Path('generated.txt').write_text('temporary output')
''',
        "assertion": "def test_failure():\n    assert 1 == 2\n",
        "timeout": "import time\ndef test_slow():\n    time.sleep(20)\n",
        "output": "def test_output():\n    print('x' * 100000)\n",
    }
    sha = repository(tmp_path, sources[scenario])
    monkeypatch.setattr(settings, "ci_sandbox_enabled", True)
    monkeypatch.setattr(settings, "ci_sandbox_timeout_seconds", 1 if scenario == "timeout" else 15)
    task_id = uuid4()
    result = ci_sandbox.reproduce(tmp_path, sha, ["python", "-m", "pytest", "-q", "-s"], ".", str(task_id))
    expected = {"isolation": "passed", "assertion": "failed", "timeout": "timeout", "output": "passed"}[scenario]
    assert result["status"] == expected, result
    assert not (tmp_path / "generated.txt").exists()
    if scenario == "output":
        assert result["output_truncated"] and len(result["output"].encode()) <= ci_sandbox.MAX_OUTPUT
    inspection = subprocess.run(["docker", "container", "inspect", f"codepilot-ci-{task_id.hex}"], capture_output=True)
    assert inspection.returncode != 0
