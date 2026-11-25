"""Bring the database schema up to date with Alembic migrations.

Run automatically when the app starts, or by hand:

    python -m app.db_upgrade

A database created before migrations existed already has every table of the
baseline, so it is stamped at the baseline instead of being created again.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .database import engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASELINE_REVISION = "0001_baseline"


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["configure_logger"] = False
    return config


def upgrade_database() -> None:
    config = alembic_config()
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "records" in tables:
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")


if __name__ == "__main__":
    upgrade_database()
    print("database is up to date")
