import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Default to SQLite (no setup required!)
    DATABASE_URL = "sqlite:///scrapai.db"

# Create engine
engine = create_engine(DATABASE_URL)

# Enable WAL mode for SQLite (better concurrency and performance)
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    if 'sqlite' in DATABASE_URL:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # Balance speed/safety
        cursor.execute("PRAGMA cache_size=-64000")   # 64MB cache
        cursor.close()

def is_postgres():
    """Check if we're using PostgreSQL"""
    return 'postgresql' in DATABASE_URL or 'postgres' in DATABASE_URL

def is_sqlite():
    """Check if we're using SQLite"""
    return 'sqlite' in DATABASE_URL

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create scoped session for thread safety
db_session = scoped_session(SessionLocal)

# Base class for models
Base = declarative_base()
Base.query = db_session.query_property()

def get_db():
    """Dependency for getting DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    import core.models  # Import models so they are registered with Base
    Base.metadata.create_all(bind=engine)
