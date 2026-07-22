"""
database.py
------------
SQLAlchemy engine/session setup for Neon Postgres.

Set the connection string via environment variable DATABASE_URL, e.g.:

    export DATABASE_URL="postgresql://<user>:<password>@<ep-xxxx>.neon.tech/<dbname>?sslmode=require"

Get this exact string from your Neon dashboard -> Connection Details.
Never commit it -- put it in a local .env file (see .env.example) and load
it with python-dotenv, or set it in your deployment platform's env vars.
"""

import os
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Loads backend/.env automatically (no-op if the file doesn't exist, e.g.
# in production where env vars are set by the platform instead). Path is
# resolved relative to this file, not the process's cwd, so `uvicorn
# main:app` from backend/ and `python db/run_migration.py ...` both find
# it regardless of where they're invoked from. This means DATABASE_URL
# and friends work as soon as .env exists -- no more manual
# `export $(cat .env | xargs)` step required for local dev.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DATABASE_URL = os.environ.get("DATABASE_URL")

# Lazily created so importing this module doesn't fail if DATABASE_URL
# isn't set yet (e.g. during local demo/mock-data runs).
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. Export it or add it to a .env file "
                "(see .env.example) before using real-DB mode."
            )
        # Neon requires SSL; pool_pre_ping avoids stale-connection errors on
        # serverless Postgres, which can suspend idle connections.
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args={"connect_timeout": 10},
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


@contextmanager
def get_session():
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def is_db_configured() -> bool:
    return bool(DATABASE_URL)
