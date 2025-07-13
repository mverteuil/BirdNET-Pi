import os

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from models.database_models import Base, Detection


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.engine = None
        self.SessionLocal = None

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

    def add_detection(self, detection_data: dict) -> Detection:
        """Adds a new detection record to the database."""
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

    def get_all_detections(self):
        """Retrieves all detection records from the database."""
        db = self.SessionLocal()
        try:
            return db.query(Detection).all()
        except SQLAlchemyError as e:
            print(f"Error retrieving detections: {e}")
            raise
        finally:
            db.close()

    # Add more CRUD methods as needed for Detection and AudioFile models

    def import_detections_from_csv(self, csv_file_path: str):
        """Imports detection records from a CSV file into the database."""
        import csv
        from datetime import datetime

        db = self.SessionLocal()
        try:
            with open(csv_file_path, "r") as f:
                reader = csv.reader(f, delimiter=";")
                next(reader)  # Skip header row
                for row in reader:
                    if not row:  # Skip empty rows
                        continue
                    try:
                        # Assuming the order: Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;Cutoff;Week;Sens;Overlap
                        (
                            date_str,
                            time_str,
                            sci_name,
                            com_name,
                            confidence_str,
                            lat_str,
                            lon_str,
                            cutoff_str,
                            week_str,
                            sens_str,
                            overlap_str,
                        ) = row

                        # Combine date and time strings and parse
                        timestamp_str = f"{date_str} {time_str}"
                        timestamp = datetime.strptime(
                            timestamp_str, "%Y-%m-%d %H:%M:%S"
                        )

                        detection = Detection(
                            species=f"{com_name} ({sci_name})",  # Combine for species name
                            confidence=float(confidence_str),
                            timestamp=timestamp,
                            audio_file_path="",  # This information is not in BirdDB.txt
                            # Add other fields if they map directly to Detection model
                        )
                        db.add(detection)
                    except ValueError as ve:
                        print(
                            f"Skipping row due to data conversion error: {row} - {ve}"
                        )
            db.commit()
            print(f"Successfully imported detections from {csv_file_path}")
        except SQLAlchemyError as e:
            db.rollback()
            print(f"Error importing detections from CSV: {e}")
            raise
        except FileNotFoundError:
            print(f"CSV file not found at {csv_file_path}")
        finally:
            db.close()

    def clear_database(self):
        """Clears all data from the database tables."""
        try:
            db = self.SessionLocal()
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
