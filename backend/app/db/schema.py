"""Explicit, additive adoption of legacy demo databases. Never drop user data."""
from sqlalchemy import inspect, text
from app.db.models import Base

REVISION = "0002_ci_sandbox"


def upgrade_schema(connection):
    Base.metadata.create_all(connection)
    additions = {
        "users": {"role": "VARCHAR(80) DEFAULT 'owner'", "api_token_hash": "VARCHAR(64)"},
        "repositories": {"provider": "VARCHAR(80) DEFAULT 'github'", "api_base_url": "TEXT", "clone_url": "TEXT", "local_path": "TEXT", "checkout_mode": "VARCHAR(80) DEFAULT 'managed'", "github_token_encrypted": "TEXT"},
        "workflow_runs": {"jobs": "JSON"},
        **{name: {"pr_id": "UUID", "pr_number": "INTEGER"} for name in ("code_symbols", "code_relations")},
        **{name: {"conversation_id": "UUID"} for name in ("chat_messages", "chat_sessions", "agent_runs", "evidence_items")},
        **{name: {key: "JSON" for key in ("facts", "tasks", "user_preferences", "repo_context", "citations")} for name in ("thread_memories", "conversation_memories")},
    }
    for table, columns in additions.items():
        existing = {col["name"] for col in inspect(connection).get_columns(table)}
        for name, sql_type in columns.items():
            if name not in existing:
                connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql_type}'))
    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_api_token_hash ON users (api_token_hash)"))
    columns = {col["name"] for col in inspect(connection).get_columns("repositories")}
    if "sync_status" not in columns:
        connection.execute(text("ALTER TABLE repositories ADD COLUMN sync_status VARCHAR(40) DEFAULT 'not_started'"))
    if "sync_errors" not in columns:
        connection.execute(text("ALTER TABLE repositories ADD COLUMN sync_errors JSON DEFAULT '[]'"))


def verify_schema(engine):
    with engine.connect() as connection:
        if "alembic_version" not in inspect(connection).get_table_names():
            raise RuntimeError("数据库尚未迁移，请先在 backend 执行 python -m alembic upgrade head")
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != REVISION:
            raise RuntimeError("数据库版本不匹配，请先执行 python -m alembic upgrade head")
