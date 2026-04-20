from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Local SQLite file for MVP. Easy to run without extra setup.
DATABASE_URL = "sqlite:///./hivemind.db"

# check_same_thread=False is required for SQLite when used with FastAPI requests.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
# SessionLocal gives us one database session per request.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base is the parent class for all SQLAlchemy models.
Base = declarative_base()
