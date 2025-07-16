import csv
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, Session
from collections.abc import Generator
from typing import Any

from birdnetpi.models.database_models import Base, Detection


class DatabaseService:
    """Provides an interface for database operations."""

    def __init__(self, session_local: sessionmaker):
        self.session_local = session_local

    def get_db(self) -> Generator[Session, Any, None]:
        """Provide a database session for dependency injection."""
        db = self.session_local()
        try:
            yield db
        finally:
            db.close()

    def clear_database(self) -> None:
        """Clear all data from the database tables."""
        db = self.session_local()
        try:
            for table in Base.metadata.sorted_tables:
                db.execute(table.delete())
            db.commit()
            print("Database cleared successfully.")
        except SQLAlchemyError as e:
            db.rollback()
            print(f"Error clearing database: {e}")
            raise
        finally:
            db.close()

    

    

    

    
