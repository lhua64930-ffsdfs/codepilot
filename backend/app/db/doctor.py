"""Credential-safe database readiness checks and explicit migration CLI."""
import argparse
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.schema import verify_schema
from app.db.session import engine


def connection_target() -> dict:
    url = make_url(settings.database_url)
    return {"driver": url.drivername, "host": url.host, "port": url.port or 5432,
            "database": url.database, "username": url.username}


def database_readiness(database_engine=None) -> dict:
    target_engine = database_engine if database_engine is not None else engine
    try:
        with target_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        verify_schema(target_engine)
    except SQLAlchemyError as exc:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        message = {"28P01": "数据库账号或密码不正确，请核对 DATABASE_URL。",
                   "3D000": "配置的数据库不存在，请核对 DATABASE_URL 中的库名。"}.get(
                       sqlstate, "数据库不可达，请检查服务、主机、端口和连接配置；本地 PostgreSQL 可运行 scripts/start_postgres.ps1。")
        return {"status": "unavailable", "database": "unavailable", "schema": "unknown", "message": message}
    except RuntimeError:
        return {"status": "unavailable", "database": "ok", "schema": "migration_required",
                "message": "数据库已连接，但需要执行 python -m alembic upgrade head。"}
    return {"status": "ready", "database": "ok", "schema": "ok"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true", help="Print connection target without credentials")
    parser.add_argument("--migrate", action="store_true", help="Explicitly run alembic upgrade head before checking")
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(connection_target(), ensure_ascii=True))
        return 0
    if args.migrate:
        from alembic import command
        from alembic.config import Config
        try:
            command.upgrade(Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")), "head")
        except (SQLAlchemyError, RuntimeError):
            print(json.dumps({"status": "unavailable", "message": "迁移未完成，请检查数据库连接与迁移日志。"}, ensure_ascii=False))
            return 1
    result = database_readiness()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
