from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.db.base import Base
from app.main import app
from app.services.presence import presence


@pytest.fixture
def client(monkeypatch, tmp_path: Path) -> Generator[TestClient, None, None]:
    """In-memory SQLite for isolated, fast API/WebSocket tests."""
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    main_module = importlib.import_module("app.main")
    ws_module = importlib.import_module("app.api.v1.endpoints.websocket")
    chat_module = importlib.import_module("app.services.chat")
    media_module = importlib.import_module("app.api.v1.endpoints.media")
    storage_module = importlib.import_module("app.services.media")
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(ws_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(chat_module, "get_session_factory", lambda: factory)
    fake_settings = SimpleNamespace(upload_path=tmp_path, max_upload_mb=1)
    monkeypatch.setattr(media_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(storage_module, "get_settings", lambda: fake_settings)
    presence._connections.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    presence._connections.clear()
    engine.dispose()


def make_user(client: TestClient, name: str) -> tuple[int, dict[str, str]]:
    user = client.post("/api/v1/auth/register", json={
        "username": name, "display_name": name.title(), "password": "very-secret-password",
    })
    assert user.status_code == 201, user.text
    logged_in = client.post("/api/v1/auth/login", json={
        "username": name, "password": "very-secret-password",
    })
    assert logged_in.status_code == 200, logged_in.text
    return user.json()["id"], {"Authorization": "Bearer " + logged_in.json()["access_token"]}
