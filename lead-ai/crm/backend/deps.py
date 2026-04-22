"""
Shared FastAPI dependencies.
Kept in a separate module so auth.py can import get_db without creating a
circular import with main.py.
"""

from database import SessionLocal


def get_db():
    """Yield a SQLAlchemy database session and ensure it is closed afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
