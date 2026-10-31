"""Bounded, offline CI reproduction. Repository code only runs in a Linux container.

No host mounts, live checkout modifications, credentials, runtime installs or shell
interpolation. The operator builds/approves the image; requests cannot select it.
"""
import asyncio
import io
import re
import subprocess
import tarfile
import threading
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import UUID

from app.core.config import settings
from app.db.models import AnalysisResult, Repository, WorkflowRun
from app.db.session import SessionLocal
from app.services.workspace_tools import _repo_checkout_path

MAX_SNAPSHOT = 32 * 1024 * 1024
MAX_OUTPUT = 64 * 1024
MAX_FILES = 3000
TERMINAL = {"passed", "failed", "timeout", "blocked", "error", "interrupted"}
_RUN_LOCK = threading.Lock()


def validate_request(command: list[str], directory: str) -> None:
    # Start small: pytest only. Tests themselves are untrusted executable code.
    if command[:3] != ["python", "-m", "pytest"]:
        raise ValueError("首版仅支持 python -m pytest，依赖必须预装在沙盒镜像中。")
    if len(command) > 32 or any(not isinstance(arg, str) or len(arg) > 500 or "\x00" in arg for arg in command):
        raise ValueError("复现命令参数不合法。")
    path = PurePosixPath(directory)
    if not directory or path.is_absolute() or ".." in path.parts or "\\" in directory or ":" in directory or "\x00" in directory:
        raise ValueError("工作目录必须是仓库内的相对路径。")


def _capture(args: list[str], *, timeout: int, limit: int, data: bytes | None = None, cwd=None, strict=False):
    """Drain output without unbounded communicate() buffering or pipe deadlocks."""
    process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = bytearray()
    overflow = threading.Event()

    def read():
        while chunk := process.stdout.read(8192):
            remaining = max(0, limit - len(output))
            output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                overflow.set()
                if strict:
                    process.kill()

    def write():
        try:
            process.stdin.write(data)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    writer = None
    if data is not None:
        writer = threading.Thread(target=write, daemon=True)
        writer.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    finally:
        reader.join(timeout=5)
        if writer:
            writer.join(timeout=5)
        process.stdout.close()
        if process.stdin:
            process.stdin.close()
    if strict and (overflow.is_set() or timed_out or process.returncode):
        raise ValueError("无法读取指定提交，或仓库快照超过 32 MiB/处理时间限制；请先同步包含该提交的仓库。")
    return process.returncode, bytes(output), timed_out, overflow.is_set()


def _safe_member(member: tarfile.TarInfo) -> bool:
    path = PurePosixPath(member.name)
    if not member.isfile() or path.is_absolute() or ".." in path.parts or "\\" in member.name:
        return False
    excluded = {".git", ".ssh", ".aws", "node_modules", ".venv", "venv", ".next", "__pycache__"}
    if any(part.lower() in excluded for part in path.parts):
        return False
    name = path.name.lower()
    return not (name == ".env" or name.startswith(".env.") or name in {".npmrc", ".pypirc", "id_rsa", "id_ed25519", "credentials"}
                or name.endswith((".pem", ".key", ".p12", ".pfx")))


def snapshot(checkout, sha: str) -> bytes:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha or ""):
        raise ValueError("缺少失败提交的完整 SHA，请重新同步 CI 记录。")
    # Only tracked content at the exact SHA; never copy .git or the live filesystem.
    _, archive, _, _ = _capture(["git", "archive", "--format=tar", sha], cwd=str(checkout),
                               timeout=30, limit=MAX_SNAPSHOT, strict=True)
    result = io.BytesIO()
    total = count = 0
    with tarfile.open(fileobj=io.BytesIO(archive)) as source, tarfile.open(fileobj=result, mode="w") as target:
        for member in source:
            if not _safe_member(member):
                continue
            count += 1
            total += member.size
            if count > MAX_FILES or total > MAX_SNAPSHOT:
                raise ValueError("仓库快照超过文件数或大小限制。")
            clean = tarfile.TarInfo(member.name)
            clean.size = member.size
            clean.mode = 0o755 if member.mode & 0o111 else 0o644
            target.addfile(clean, source.extractfile(member))
    return result.getvalue()


def docker_command(name: str, command: list[str], directory: str) -> list[str]:
    timeout = max(1, min(settings.ci_sandbox_timeout_seconds, 600))
    memory = max(128, min(settings.ci_sandbox_memory_mb, 2048))
    cpus = max(0.1, min(settings.ci_sandbox_cpus, 2.0))
    return ["docker", "run", "--rm", "--pull=never", "--name", name,
            "--label", "codepilot.ci-sandbox=true", "--network=none", "--read-only",
            "--user=10001:10001", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            f"--memory={memory}m", f"--memory-swap={memory}m", f"--cpus={cpus}", "--pids-limit=64",
            "--ulimit", "nofile=256:256", "--log-driver=none", "--ipc=none",
            "--tmpfs", "/workspace:rw,nosuid,nodev,size=128m,uid=10001,gid=10001,mode=0700",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=32m,mode=1777",
            "--workdir=/workspace", "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint=python", "-i", settings.ci_sandbox_image,
            "-I", "/opt/codepilot/runner.py", str(timeout), directory, *command]


def reproduce(checkout, sha: str, command: list[str], directory: str, task_id: str) -> dict:
    validate_request(command, directory)
    result = {"status": "blocked", "commit_sha": sha, "command": command, "working_directory": directory,
              "image": settings.ci_sandbox_image, "exit_code": None, "output": "", "output_truncated": False,
              "message": "", "finished_at": None}
    if not settings.ci_sandbox_enabled:
        return {**result, "message": "CI 沙盒未启用，请按部署文档构建镜像并启用。"}
    # Deterministic names allow cleanup of a previous crashed attempt before reuse.
    name = f"codepilot-ci-{UUID(task_id).hex}"
    if not _RUN_LOCK.acquire(blocking=False):
        return {**result, "message": "当前执行服务已有复现任务，请稍后重新提交。"}
    try:
        data = snapshot(checkout, sha)
        _capture(["docker", "rm", "-f", name], timeout=10, limit=4096)
        code, output, timed_out, truncated = _capture(docker_command(name, command, directory),
            timeout=max(1, min(settings.ci_sandbox_timeout_seconds, 600)) + 15, limit=MAX_OUTPUT, data=data)
        text = output.decode("utf-8", errors="replace")
        status = "timeout" if timed_out or code == 124 else "passed" if code == 0 else "blocked" if code in {125, 126, 127} else "failed"
        message = {"passed": "所选测试通过，未在该隔离环境复现失败；不代表原 CI 已恢复。",
                   "failed": "验证命令执行失败；请核对日志是否与原 CI 错误一致，依赖或环境缺失也会失败。",
                   "timeout": "复现超过时间限制，任务已终止。",
                   "blocked": "沙盒启动或测试环境不可用，请检查 Docker、镜像和预装依赖。"}[status]
        result.update(status=status, exit_code=code, output=text, output_truncated=truncated, message=message)
    except (ValueError, OSError, tarfile.TarError) as exc:
        result["message"] = str(exc)
    finally:
        try:
            _capture(["docker", "rm", "-f", name], timeout=10, limit=4096)
            # --rm may already have removed it. Cleanup is intentionally idempotent.
        except OSError:
            pass
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        _RUN_LOCK.release()
    return result


async def execute_ci_reproduction(analysis_id: UUID) -> None:
    with SessionLocal() as db:
        row = db.get(AnalysisResult, analysis_id)
        if row is None or row.result_json.get("status") in TERMINAL:
            return
        if row.result_json.get("status") == "running":
            # Queue lease recovery must never blindly replay untrusted test code.
            try:
                await asyncio.to_thread(_capture, ["docker", "rm", "-f", f"codepilot-ci-{analysis_id.hex}"], timeout=10, limit=4096)
            except OSError:
                pass
            row.result_json = {**row.result_json, "status": "interrupted", "message": "执行服务中断，未自动重跑；可手动提交新任务。"}
            db.commit()
            return
        run = db.get(WorkflowRun, row.target_id)
        repo = db.get(Repository, run.repo_id) if run else None
        if repo is None:
            row.result_json = {"status": "blocked", "message": "仓库或 CI 记录已删除。"}
            db.commit()
            return
        request = row.input_snapshot
        checkout = _repo_checkout_path(repo)
        row.result_json = {**row.result_json, "status": "running"}
        db.commit()
        result = await asyncio.to_thread(reproduce, checkout, request["commit_sha"], request["command"], request["working_directory"], str(analysis_id))
        row.result_json = result
        db.commit()


def latest_reproduction(db, run_id) -> AnalysisResult | None:
    return db.query(AnalysisResult).filter_by(target_type="workflow_run", target_id=run_id, analysis_type="ci_reproduction").order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc()).first()
