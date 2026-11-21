from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import get_engine
import app.models  # noqa: F401 - registers all table mappings


def init_db() -> None:
    with get_engine().begin() as connection:
        # Serialize the schema check and update across concurrent startups.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        Base.metadata.create_all(bind=connection)
        columns = inspect(connection).get_columns("conversations")
        if not any(column["name"] == "ended_by" for column in columns):
            connection.exec_driver_sql(
                "ALTER TABLE conversations ADD COLUMN ended_by INTEGER NOT NULL DEFAULT 0"
            )


if __name__ == "__main__":
    init_db()
    print("Initialized the database schema.")
