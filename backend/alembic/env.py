from alembic import context
from app.db.session import engine
from app.db.models import Base

if context.is_offline_mode():
    raise RuntimeError("Legacy adoption requires an online database connection")
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()
