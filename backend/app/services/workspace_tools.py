"""Path confinement and text access for repository workspaces."""
import os
import re
from pathlib import Path
from app.core.config import settings
from app.db.models import Repository

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".nuxt",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
WORKSPACE_SECRET_FILENAMES = {".env", ".env.local", ".env.production", ".npmrc", ".pypirc"}
WORKSPACE_TEXT_FILENAMES = {"Dockerfile", "Makefile", "README", "LICENSE", "package.json", "requirements.txt", "pyproject.toml"}
WORKSPACE_TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".md",
    ".mdx",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".sql",
    ".sh",
    ".ps1",
    ".bat",
    ".cmd",
    ".html",
    ".css",
    ".scss",
}


def _checkout_root() -> Path:
    root = Path(settings.repo_checkout_dir)
    if not root.is_absolute():
        root = BACKEND_ROOT / root
    return root.resolve()


def _repo_checkout_path(repo: Repository) -> Path:
    local_path = getattr(repo, "local_path", None)
    if local_path:
        path = Path(os.path.expandvars(os.path.expanduser(str(local_path))))
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        resolved = path.resolve()
        if resolved.exists():
            return resolved

    safe_name = repo.full_name.replace("/", "__").replace("\\", "__")
    checkout_root = _checkout_root()
    expected = (checkout_root / f"{repo.id}-{safe_name}").resolve()
    if expected.exists():
        return expected

    # 仓库记录可能被删除后重建，而本地 clone 仍保留旧 UUID。
    # 复用同名 checkout，避免工作区工具静默失去源码访问能力。
    candidates = [
        path
        for path in checkout_root.glob(f"*-{safe_name}")
        if path.is_dir() and path.resolve() != expected
    ]
    if candidates:
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0].resolve()
    return expected


def _workspace_root(repo: Repository | None) -> Path:
    if repo is None:
        return PROJECT_ROOT
    checkout_path = _repo_checkout_path(repo)
    if not checkout_path.exists():
        raise ValueError(
            f"{repo.full_name} 的仓库代码还没有克隆到本地。"
            "读取源码前，请先同步仓库或重新连接仓库。"
        )
    return checkout_path


def _workspace_relative(path: Path, workspace_root: Path) -> str:
    return path.relative_to(workspace_root).as_posix()


def _workspace_path(workspace_root: Path, raw_path: str | None = None) -> Path:
    normalized_path = str(raw_path or ".").strip()
    if normalized_path in {"", ".", "./", "/", "\\"}:
        normalized_path = "."
    elif not re.match(r"^[a-zA-Z]:", normalized_path):
        normalized_path = normalized_path.lstrip("/\\") or "."
    candidate = (workspace_root / normalized_path).resolve()
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("路径位于项目工作区之外。") from exc
    if any(part in WORKSPACE_SKIP_DIRS for part in candidate.relative_to(workspace_root).parts):
        raise ValueError("路径位于被跳过的工作区目录中。")
    if candidate.name in WORKSPACE_SECRET_FILENAMES:
        raise ValueError("不会向对话 Agent 暴露敏感配置文件。")
    return candidate


def _is_workspace_text(path: Path) -> bool:
    if path.name in WORKSPACE_SECRET_FILENAMES or path.suffix.lower() in {".log", ".db", ".sqlite", ".sqlite3"}:
        return False
    return path.name in WORKSPACE_TEXT_FILENAMES or path.suffix.lower() in WORKSPACE_TEXT_EXTENSIONS or path.name.lower().endswith("dockerfile")


def _iter_workspace_files(root: Path, workspace_root: Path, max_files: int = 1000):
    if root.is_file():
        yield root
        return
    count = 0
    for path in root.rglob("*"):
        if count >= max_files:
            break
        if not path.is_file():
            continue
        relative_parts = path.relative_to(workspace_root).parts
        if any(part in WORKSPACE_SKIP_DIRS for part in relative_parts):
            continue
        if not _is_workspace_text(path):
            continue
        count += 1
        yield path


def _read_workspace_text(path: Path, max_bytes: int = 250_000) -> str:
    if not path.exists() or not path.is_file():
        raise ValueError("未找到工作区文件。")
    if not _is_workspace_text(path):
        raise ValueError("只能读取非敏感的文本工作区文件。")
    data = path.read_bytes()
    if len(data) > max_bytes or b"\x00" in data[:4096]:
        raise ValueError("文件过大，或看起来是二进制文件。")
    for encoding in ["utf-8-sig", "utf-8", "gb18030", "latin-1"]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法将工作区文件解码为文本。")


