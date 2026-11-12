"""ASGI entry point.

    cd backend && uvicorn app.main:app --reload
"""

from app.api import create_app

app = create_app()
