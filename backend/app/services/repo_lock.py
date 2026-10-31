"""Reject overlapping syncs; PostgreSQL advisory locks span API processes."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
from weakref import WeakValueDictionary

from fastapi import HTTPException
from sqlalchemy import text

_locks = WeakValueDictionary()


@asynccontextmanager
async def repository_sync_lock(db, repo_id):
    key = str(repo_id)
    lock = _locks.setdefault(key, asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "仓库正在同步，请稍后重试")
    async with lock:
        connection = None
        acquired = False
        lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
        try:
            if db.get_bind().dialect.name == "postgresql":
                connection = db.get_bind().connect()
                acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id})
                if not acquired:
                    raise HTTPException(409, "仓库正在其他进程中同步")
            yield
        finally:
            if connection is not None:
                try:
                    if acquired:
                        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
                finally:
                    connection.close()
