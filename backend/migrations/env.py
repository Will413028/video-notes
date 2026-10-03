import os

from alembic import context

from app.database import Base, build_engine

url = os.environ.get("VIDEO_NOTES_DATABASE_URL")
if not url:
    raise RuntimeError("請設定 VIDEO_NOTES_DATABASE_URL。")
engine = build_engine(url)
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
