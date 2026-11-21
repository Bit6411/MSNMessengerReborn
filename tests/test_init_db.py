from importlib import import_module

from fastapi import BackgroundTasks
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.endpoints.conversations import end_conversation_endpoint
from app.db.base import Base
from app.models import Attachment, Conversation, Message, User


def test_init_db_upgrades_existing_conversations(monkeypatch, tmp_path):
    database = import_module("app.db.init_db")
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    monkeypatch.setattr(database, "get_engine", lambda: engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE conversations ("
            "id INTEGER PRIMARY KEY, user_low_id INTEGER NOT NULL, "
            "user_high_id INTEGER NOT NULL, scope_key VARCHAR(150) NOT NULL UNIQUE, "
            "status_id INTEGER, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "INSERT INTO conversations (user_low_id, user_high_id, scope_key) "
            "VALUES (1, 2, 'dm:1:2')"
        )

    database.init_db()
    database.init_db()

    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT scope_key, ended_by FROM conversations"
        ).one()
        assert row == ("dm:1:2", 0)
    engine.dispose()


def test_end_conversation_with_legacy_messages_and_attachments(monkeypatch, tmp_path):
    database = import_module("app.db.init_db")
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    monkeypatch.setattr(database, "get_engine", lambda: engine)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES conversations (id),
                sender_id INTEGER NOT NULL REFERENCES users (id),
                text TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.exec_driver_sql(
            "CREATE INDEX ix_messages_conversation_id_id ON messages (conversation_id, id)"
        )
        Base.metadata.create_all(connection)

    with Session(engine) as db:
        alice = User(username="alice", display_name="Alice", password_hash="unused")
        bob = User(username="bob", display_name="Bob", password_hash="unused")
        db.add_all([alice, bob])
        db.flush()
        conversation = Conversation(user_low_id=alice.id, user_high_id=bob.id, scope_key="dm:1:2")
        db.add(conversation)
        db.flush()
        message = Message(conversation_id=conversation.id, sender_id=alice.id, text="Hello")
        db.add(message)
        db.flush()
        attachment = Attachment(
            conversation_id=conversation.id, uploader_id=alice.id, message_id=message.id,
            stored_name="example.png", original_name="example.png",
            content_type="image/png", size_bytes=8,
        )
        db.add(attachment)
        alice_id, bob_id, conversation_id = alice.id, bob.id, conversation.id
        message_id = message.id
        db.commit()
        attachment_id = attachment.id

    database.init_db()
    database.init_db()

    with Session(engine) as db:
        assert db.connection().exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert db.get(Message, message_id).text == "Hello"
        assert db.get(Attachment, attachment_id).message_id == message_id
        first = BackgroundTasks()
        end_conversation_endpoint(conversation_id, first, db, db.get(User, alice_id))
        notification = first.tasks[0].args[1]
        assert notification.sender_id is None
        assert db.get(Message, notification.id).text == "🔔 Alice has ended this conversation."

        second = BackgroundTasks()
        end_conversation_endpoint(conversation_id, second, db, db.get(User, bob_id))
        assert second.tasks[0].func.__name__ == "publish_conversation_deleted"
        assert db.get(Conversation, conversation_id) is None
        assert db.get(Attachment, attachment_id) is None
        assert db.get(Message, message_id) is None
        assert db.get(Message, notification.id) is None
    engine.dispose()
