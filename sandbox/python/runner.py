"""Trusted image entry point. No repository code runs during extraction."""
import os
import signal
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath

timeout, directory, *command = sys.argv[1:]
root = Path("/workspace")
total = count = 0
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|*") as archive:
    for member in archive:
        path = PurePosixPath(member.name)
        if not member.isfile() or path.is_absolute() or ".." in path.parts or "\\" in member.name:
            raise ValueError("Unsafe snapshot member")
        count += 1
        total += member.size
        if count > 3000 or total > 32 * 1024 * 1024:
            raise ValueError("Snapshot limit exceeded")
        destination = root / member.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as target:
            target.write(archive.extractfile(member).read())
        destination.chmod(member.mode & 0o777)
cwd = (root / directory).resolve()
cwd.relative_to(root)
process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, start_new_session=True)
try:
    sys.exit(process.wait(timeout=int(timeout)))
except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGKILL)
    process.wait()
    print("CodePilot: reproduction timed out", flush=True)
    sys.exit(124)
