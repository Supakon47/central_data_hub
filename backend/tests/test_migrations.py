"""Migrations must build exactly the schema the models describe."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from app.database import Base, engine
from app.db_upgrade import upgrade_database


def schema_differences() -> list:
    with engine.connect() as connection:
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)


def current_revision() -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def drop_everything() -> None:
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_migrations_build_the_model_schema_on_an_empty_database():
    drop_everything()
    upgrade_database()
    assert "records" in inspect(engine).get_table_names()
    assert schema_differences() == []
    assert current_revision() is not None


def test_a_database_from_before_migrations_is_stamped_not_recreated():
    drop_everything()
    Base.metadata.create_all(bind=engine)  # how the app created tables before Alembic
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO data_sources (name, connection_type, classification, is_active) "
            "VALUES ('kept', 'xlsx_import', 'internal', 1)"
        ))
    upgrade_database()
    assert current_revision() is not None
    with engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM data_sources")).scalars().all() == ["kept"]


def test_upgrading_twice_changes_nothing():
    drop_everything()
    upgrade_database()
    upgrade_database()
    assert schema_differences() == []
