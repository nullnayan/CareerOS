"""
Creates the connection to Postgres and gives us a way to open a
"session" (a temporary connection used for one request) whenever we need
to read or write data.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load environment variables from .env
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://careeros:careeros_dev_password@localhost:5432/careeros"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Used by FastAPI routes to get a database session for one request,
    and guarantees it's closed afterward even if an error happens."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
