import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.doctor import connection_target, database_readiness
from app.db.schema import REVISION
from app.db.session import create_database_engine


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    yield engine
    engine.dispose()


def mark_migrated(engine, revision=REVISION):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision})


def test_connected_database_requires_current_migration(database):
    assert database_readiness(database)["schema"] == "migration_required"
    mark_migrated(database, "0001_reliability")
    assert database_readiness(database)["schema"] == "migration_required"
    with database.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num=:revision"), {"revision": REVISION})
    assert database_readiness(database) == {"status": "ready", "database": "ok", "schema": "ok"}


def test_connection_error_is_actionable_and_does_not_expose_credentials():
    class Unavailable:
        def connect(self):
            raise OperationalError("connect", {}, Exception("postgresql://user:secret-password@localhost/private"))
    result = database_readiness(Unavailable())
    assert result["database"] == "unavailable"
    assert "start_postgres.ps1" in result["message"]
    assert "secret-password" not in str(result)


@pytest.mark.parametrize("sqlstate,hint", [("28P01", "账号或密码"), ("3D000", "数据库不存在")])
def test_database_error_classification(sqlstate, hint):
    class DriverError(Exception): pass
    error = DriverError("secret-driver-details")
    error.sqlstate = sqlstate
    class Unavailable:
        def connect(self):
            raise OperationalError("connect", {}, error)
    assert hint in database_readiness(Unavailable())["message"]


@pytest.mark.asyncio
async def test_readiness_http_status_matches_actual_database(database, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "engine", database)
    app = main.create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health")).status_code == 200
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["schema"] == "migration_required"
        mark_migrated(database)
        response = await client.get("/health/ready")
        assert response.status_code == 200 and response.json()["status"] == "ready"


def test_sqlite_still_connects_without_postgres_driver_options():
    engine = create_database_engine("sqlite://")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1
    engine.dispose()


def test_describe_target_omits_password_and_url_secrets(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://devflow:do-not-print@127.0.0.1:5432/devflow?sslpassword=hidden")
    target = connection_target()
    assert target["host"] == "127.0.0.1" and target["database"] == "devflow"
    assert "do-not-print" not in str(target) and "hidden" not in str(target)
