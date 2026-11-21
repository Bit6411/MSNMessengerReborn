from sqlalchemy import Connection, inspect

from app.db.base import Base
from app.db.session import get_engine
import app.models  # noqa: F401 - registers all table mappings


def allow_system_messages(connection: Connection) -> None:
    columns = inspect(connection).get_columns("messages")
    if next(column for column in columns if column["name"] == "sender_id")["nullable"]:
        return

    schema_objects = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE tbl_name = 'messages' "
        "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
    ).scalars().all()
    connection.exec_driver_sql("""
        CREATE TABLE messages_new (
            id INTEGER PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES conversations (id),
            sender_id INTEGER REFERENCES users (id),
            text TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.exec_driver_sql("""
        INSERT INTO messages_new (id, conversation_id, sender_id, text, created_at)
        SELECT id, conversation_id, sender_id, text, created_at FROM messages
    """)
    connection.exec_driver_sql("DROP TABLE messages")
    connection.exec_driver_sql("ALTER TABLE messages_new RENAME TO messages")
    for statement in schema_objects:
        connection.exec_driver_sql(statement)


def init_db() -> None:
    with get_engine().connect() as connection:
        # SQLite requires foreign keys to be disabled outside the transaction
        # when rebuilding a referenced table. This setting is connection-local.
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            with connection.begin():
                # Serialize the schema check and update across concurrent startups.
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                Base.metadata.create_all(bind=connection)
                columns = inspect(connection).get_columns("conversations")
                if not any(column["name"] == "ended_by" for column in columns):
                    connection.exec_driver_sql(
                        "ALTER TABLE conversations ADD COLUMN ended_by INTEGER NOT NULL DEFAULT 0"
                    )
                allow_system_messages(connection)
        finally:
            if foreign_keys:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")


if __name__ == "__main__":
    init_db()
    print("Initialized the database schema.")
