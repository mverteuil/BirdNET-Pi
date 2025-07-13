import os

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from models.database_models import Base
from services.database_service import DatabaseService


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.engine = None
        self.SessionLocal = None
        self.db_service = None

    def initialize_database(self):
        """Initializes the database engine and creates tables if they don't exist."""
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

    def get_db(self):
        """Dependency to get a database session."""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Delegate CRUD operations to DatabaseService
    def add_detection(self, detection_data: dict):
        return self.db_service.add_detection(detection_data)

    def get_all_detections(self):
        return self.db_service.get_all_detections()

    def import_detections_from_csv(self, csv_file_path: str):
        return self.db_service.import_detections_from_csv(csv_file_path)

    def clear_database(self):
        return self.db_service.clear_database()
