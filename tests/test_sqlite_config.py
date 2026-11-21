from app.core.config import PROJECT_ROOT, get_settings
from app.db.session import get_engine


def test_sqlite_database_configuration():
    settings = get_settings()
    assert settings.sqlite_path.is_absolute()
    assert settings.database_url.database == str(settings.sqlite_path)
    assert settings.database_url.drivername == "sqlite+pysqlite"
    assert get_engine().dialect.name == "sqlite"


def test_gitignore_excludes_sqlite_database():
    text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.db" in text and "*.db-wal" in text and "*.db-shm" in text
