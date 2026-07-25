from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from naratrace.core.paths import LocalPaths, ensure_local_directories, get_local_paths
from naratrace.database.session import configure_database


def init_database(paths: LocalPaths | None = None) -> Path:
    paths = ensure_local_directories(paths or get_local_paths())
    configure_database(paths.database_url)
    run_migrations(paths.database_url)
    return paths.database_file


def run_migrations(database_url: str) -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    alembic_ini = backend_dir / "alembic.ini"
    alembic_dir = backend_dir / "alembic"

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(alembic_dir))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
