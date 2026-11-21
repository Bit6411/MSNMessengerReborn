from app.db.base import Base
from app.db.session import get_engine
import app.models  # noqa: F401 - registers all table mappings


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())


if __name__ == "__main__":
    init_db()
    print("Created missing tables (existing tables were not modified).")
