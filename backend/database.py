from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Always resolve DB path from project root, not current shell cwd.
# This avoids "missing data" when the server is started from another folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_FILE = PROJECT_ROOT / "hivemind.db"
DATABASE_URL = f"sqlite:///{DATABASE_FILE.as_posix()}"

# check_same_thread=False is required for SQLite when used with FastAPI requests.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
# SessionLocal gives us one database session per request.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base is the parent class for all SQLAlchemy models.
Base = declarative_base()
