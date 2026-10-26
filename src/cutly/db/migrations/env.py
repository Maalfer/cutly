"""Entorno de Alembic: usa el mismo motor (y PRAGMAs) que la aplicación."""

from alembic import context
from sqlmodel import SQLModel

from cutly.db import models  # noqa: F401  (registra las tablas)
from cutly.db.session import get_engine

target_metadata = SQLModel.metadata


def run_migrations_online() -> None:
    with get_engine().connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite no soporta ALTER completo: se reconstruye la tabla
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
