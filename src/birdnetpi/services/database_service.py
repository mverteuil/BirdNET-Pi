import csv
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from birdnetpi.models.database_models import Base, Detection


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

    def get_detection_counts_by_date_range(
        self, start_date: datetime, end_date: datetime
    ) -> dict:
        """Get total detection count and unique species count within a date range."""
        db = self.session_local()
        try:
            total_count = (
                db.query(Detection)
                .filter(Detection.timestamp.between(start_date, end_date))
                .count()
            )
            unique_species_count = (
                db.query(Detection.com_name)
                .filter(Detection.timestamp.between(start_date, end_date))
                .distinct()
                .count()
            )
            return {"total_count": total_count, "unique_species": unique_species_count}
        except SQLAlchemyError as e:
            print(f"Error getting detection counts by date range: {e}")
            raise
        finally:
            db.close()

    def get_top_species_with_prior_counts(
        self,
        start_date: datetime,
        end_date: datetime,
        prior_start_date: datetime,
        prior_end_date: datetime,
    ) -> list[dict]:
        """Fetch the top 10 species for the current week and their counts from the prior week."""
        db = self.session_local()
        try:
            current_week_subquery = (
                db.query(
                    Detection.com_name,
                    func.count(Detection.com_name).label("current_count"),
                )
                .filter(Detection.timestamp.between(start_date, end_date))
                .group_by(Detection.com_name)
                .subquery()
            )

            prior_week_subquery = (
                db.query(
                    Detection.com_name,
                    func.count(Detection.com_name).label("prior_count"),
                )
                .filter(Detection.timestamp.between(prior_start_date, prior_end_date))
                .group_by(Detection.com_name)
                .subquery()
            )

            results = (
                db.query(
                    current_week_subquery.c.com_name,
                    current_week_subquery.c.current_count,
                    func.coalesce(prior_week_subquery.c.prior_count, 0).label(
                        "prior_count"
                    ),
                )
                .outerjoin(
                    prior_week_subquery,
                    current_week_subquery.c.com_name == prior_week_subquery.c.com_name,
                )
                .order_by(current_week_subquery.c.current_count.desc())
                .limit(10)
                .all()
            )

            return [
                {
                    "com_name": row.com_name,
                    "current_count": row.current_count,
                    "prior_count": row.prior_count,
                }
                for row in results
            ]
        except SQLAlchemyError as e:
            print(f"Error getting top species with prior counts: {e}")
            raise
        finally:
            db.close()

    def get_new_species_data(
        self, start_date: datetime, end_date: datetime
    ) -> list[dict]:
        """Fetch new species detected in the current week that were not present in prior data."""
        db = self.session_local()
        try:
            # Subquery to find all species detected before the start_date
            prior_species_subquery = (
                db.query(Detection.com_name)
                .filter(Detection.timestamp < start_date)
                .distinct()
                .subquery()
            )

            # Query for new species in the current range, excluding those in the prior_species_subquery
            new_species_results = (
                db.query(
                    Detection.com_name, func.count(Detection.com_name).label("count")
                )
                .filter(
                    Detection.timestamp.between(start_date, end_date),
                    ~Detection.com_name.in_(prior_species_subquery),
                )
                .group_by(Detection.com_name)
                .order_by(func.count(Detection.com_name).desc())
                .all()
            )

            return [
                {"com_name": row.com_name, "count": row.count}
                for row in new_species_results
            ]
        except SQLAlchemyError as e:
            print(f"Error getting new species data: {e}")
            raise
        finally:
            db.close()

    def get_most_recent_detections(self, limit: int = 10) -> list[dict]:
        """Retrieve the most recent detection records from the database."""
        db = self.session_local()
        try:
            recent_detections = (
                db.query(Detection)
                .order_by(Detection.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "Date": d.timestamp.strftime("%Y-%m-%d"),
                    "Time": d.timestamp.strftime("%H:%M:%S"),
                    "Sci_Name": (
                        d.species.split(" (")[1][:-1] if " (" in d.species else ""
                    ),
                    "Com_Name": (
                        d.species.split(" (")[0] if " (" in d.species else d.species
                    ),
                    "Confidence": d.confidence,
                    "Lat": d.latitude,
                    "Lon": d.longitude,
                    "Cutoff": d.cutoff,
                    "Week": d.week,
                    "Sens": d.sensitivity,
                    "Overlap": d.overlap,
                }
                for d in recent_detections
            ]
        except SQLAlchemyError as e:
            print(f"Error getting most recent detections: {e}")
            raise
        finally:
            db.close()
