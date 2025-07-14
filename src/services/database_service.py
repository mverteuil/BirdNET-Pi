import csv
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from models.database_models import Base, Detection


class DatabaseService:
    """Provides an interface for database operations."""

    def __init__(self, session_local: sessionmaker):
        self.session_local = session_local

    def add_detection(self, detection_data: dict) -> Detection:
        """Add a new detection record to the database."""
        db = self.session_local()
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
        db = self.session_local()
        try:
            return db.query(Detection).all()
        except SQLAlchemyError as e:
            print(f"Error retrieving detections: {e}")
            raise
        finally:
            db.close()

    def import_detections_from_csv(self, csv_file_path: str) -> None:
        """Import detection records from a CSV file into the database."""
        db = self.session_local()
        try:
            with open(csv_file_path) as f:
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
                    except IndexError as ie:
                        print(
                            f"Skipping row due to incorrect column count: {row} - {ie}"
                        )
                        continue  # Skip to the next row if IndexError occurs
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
