import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from birdnetpi.models.database_models import Base, Detection
from birdnetpi.services.database_service import DatabaseService


class DatabaseManager:
    """Manages database connections and delegates CRUD operations to DatabaseService."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.engine = None
        self.SessionLocal = None
        self.db_service = None

    def initialize_database(self) -> None:
        """Initialize the database engine and create tables if they don't exist."""
        try:
            # Ensure the directory for the database exists
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self.engine = create_engine(f"sqlite:///{self.db_path}")
            Base.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=self.engine
            )
            self.db_service = DatabaseService(self.SessionLocal)
            print(f"Database initialized at {self.db_path}")
        except SQLAlchemyError as e:
            print(f"Error initializing database: {e}")
            raise

    def get_db(self) -> Generator[Session, Any, None]:
        """Provide a database session for dependency injection."""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def add_detection(self, detection_data: dict) -> Detection:
        """Add a new detection record to the database."""
        db = self.SessionLocal()
        try:
            detection = Detection(**detection_data)
            db.add(detection)
            db.commit()
            db.refresh(detection)
            return detection
        except SQLAlchemyError as e:
            db.rollback()
            print(f"Error adding detection: {e}")
            raise
        finally:
            db.close()

    def get_all_detections(self) -> list[Detection]:
        """Retrieve all detection records from the database."""
        return self.db_service.get_all_detections()

    def import_detections_from_csv(self, csv_file_path: str) -> None:
        """Import detection records from a CSV file into the database."""
        return self.db_service.import_detections_from_csv(csv_file_path)

    def clear_database(self) -> None:
        """Clear all data from the database."""
        return self.db_service.clear_database()
