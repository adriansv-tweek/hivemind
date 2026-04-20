from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - defensive fallback only.
    load_dotenv = None

# Load local .env values (like OPENAI_API_KEY) from project root.
# Keep app boot resilient even if python-dotenv is missing.
if load_dotenv:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)

from .database import Base, engine
from . import models
from .routes import router

app = FastAPI(title="Hivemind API")

# Allow local frontend calls during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Create tables on startup for the MVP.
# models import is required so SQLAlchemy knows Note exists.
Base.metadata.create_all(bind=engine)
