"""
Root ASGI entrypoint wrapper.
Allows deployment platforms (Render, Railway, Heroku, etc.) to load the app using either:
  uvicorn main:app --host 0.0.0.0 --port $PORT
or
  uvicorn backend.api:app --host 0.0.0.0 --port $PORT
"""
from backend.api import app

__all__ = ["app"]
