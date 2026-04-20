from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
