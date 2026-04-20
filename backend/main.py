from fastapi import FastAPI

from .database import Base, engine
from . import models
from .routes import router

app = FastAPI(title="Hivemind API")
app.include_router(router)

# Create tables on startup for the MVP.
# models import is required so SQLAlchemy knows Note exists.
Base.metadata.create_all(bind=engine)
