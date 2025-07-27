import csv
import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func

from birdnetpi.models.database_models import AudioFile, Detection
from birdnetpi.services.database_service import DatabaseService


class DetectionManager:
    """Manages detection operations via DatabaseService."""

    def __init__(self, db_service: DatabaseService) -> None:
        self.db_service = db_service

    def add_detection(self, detection_data: dict) -> Detection:
        """Add a new detection record to the database."""
        with self.db_service.get_db() as db:
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

    def get_all_detections(self) -> list[Detection]:
        """Retrieve all detection records from the database."""
        with self.db_service.get_db() as db:
            try:
                return db.query(Detection).all()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving detections: {e}")
                raise

    def import_detections_from_csv(self, csv_file_path: str) -> None:
        """Import detection records from a CSV file into the database."""
        with self.db_service.get_db() as db:
            try:
                with open(csv_file_path) as f:
                    reader = csv.reader(f, delimiter=";")
                    next(reader)  # Skip header row
                    for row in reader:
                        if not row:  # Skip empty rows
                            continue
                        try:
                            # Date;Time;Sci_Name;Com_Name;Confidence;Lat;Lon;
                            # Cutoff;Week;Sens;Overlap
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
                            timestamp = datetime.datetime.strptime(
                                timestamp_str, "%Y-%m-%d %H:%M:%S"
                            )

                            detection = Detection(
                                species=f"{com_name} ({sci_name})",  # Combine species name
                                confidence=float(confidence_str),
                                timestamp=timestamp,
                                audio_file_path="",  # Not in BirdDB.txt
                                # Add other fields if they map directly to Detection model
                            )
                            db.add(detection)
                        except IndexError as ie:
                            print(f"Skipping row: incorrect column count ({row}) - {ie}")
                            continue  # Skip to the next row if IndexError occurs
                        except ValueError as ve:
                            print(f"Skipping row due to data conversion error: {row} - {ve}")
                db.commit()
                print(f"Successfully imported detections from {csv_file_path}")
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error importing detections from CSV: {e}")
                raise
            except FileNotFoundError:
                print(f"CSV file not found at {csv_file_path}")
                raise  # Re-raise the FileNotFoundError
            finally:
                db.close()

    def get_audio_file_by_path(self, file_path: str) -> AudioFile | None:
        """Retrieve an AudioFile record by its file path."""
        with self.db_service.get_db() as db:
            try:
                return db.query(AudioFile).filter_by(file_path=file_path).first()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving audio file: {e}")
                raise

    def delete_detection(self, detection_id: int) -> None:
        """Delete a detection record from the database."""
        with self.db_service.get_db() as db:
            try:
                detection = db.query(Detection).get(detection_id)
                if detection:
                    db.delete(detection)
                    db.commit()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error deleting detection: {e}")
                raise

    def get_detections_by_species(self, species_name: str) -> list[Detection]:
        """Retrieve all detection records for a given species from the database."""
        with self.db_service.get_db() as db:
            try:
                return db.query(Detection).filter_by(species=species_name).all()
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving detections by species: {e}")
                raise

    def get_detection_counts_by_date_range(self, start_date: datetime, end_date: datetime) -> dict:
        """Get total detection count and unique species count within a date range."""
        with self.db_service.get_db() as db:
            try:
                total_count = (
                    db.query(Detection)
                    .filter(Detection.timestamp.between(start_date, end_date))
                    .count()
                )
                unique_species_count = (
                    db.query(Detection.species)
                    .filter(Detection.timestamp.between(start_date, end_date))
                    .distinct()
                    .count()
                )
                return {
                    "total_count": total_count,
                    "unique_species": unique_species_count,
                }
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting detection counts by date range: {e}")
                raise

    def get_top_species_with_prior_counts(
        self,
        start_date: datetime,
        end_date: datetime,
        prior_start_date: datetime,
        prior_end_date: datetime,
    ) -> list[dict]:
        """Fetch top 10 species for current and prior weeks."""
        with self.db_service.get_db() as db:
            try:
                current_week_subquery = (
                    db.query(
                        Detection.species,
                        func.count(Detection.species).label("current_count"),
                    )
                    .filter(Detection.timestamp.between(start_date, end_date))
                    .group_by(Detection.species)
                    .subquery()
                )

                prior_week_subquery = (
                    db.query(
                        Detection.species,
                        func.count(Detection.species).label("prior_count"),
                    )
                    .filter(Detection.timestamp.between(prior_start_date, prior_end_date))
                    .group_by(Detection.species)
                    .subquery()
                )

                results = (
                    db.query(
                        current_week_subquery.c.species,
                        current_week_subquery.c.current_count,
                        func.coalesce(prior_week_subquery.c.prior_count, 0).label("prior_count"),
                    )
                    .outerjoin(
                        prior_week_subquery,
                        current_week_subquery.c.species == prior_week_subquery.c.species,
                    )
                    .order_by(current_week_subquery.c.current_count.desc())
                    .limit(10)
                    .all()
                )

                return [
                    {
                        "species": row.species,
                        "current_count": row.current_count,
                        "prior_count": row.prior_count,
                    }
                    for row in results
                ]
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting top species with prior counts: {e}")
                raise

    def get_new_species_data(self, start_date: datetime, end_date: datetime) -> list[dict]:
        """Fetch new species not present in prior data."""
        with self.db_service.get_db() as db:
            try:
                # Subquery to find all species detected before the start_date
                prior_species_subquery = (
                    db.query(Detection.species)
                    .filter(Detection.timestamp < start_date)
                    .distinct()
                    .subquery()
                )

                # Query for new species in current range, excluding prior_species_subquery
                new_species_results = (
                    db.query(Detection.species, func.count(Detection.species).label("count"))
                    .filter(
                        Detection.timestamp.between(start_date, end_date),
                        ~Detection.species.in_(prior_species_subquery),
                    )
                    .group_by(Detection.species)
                    .order_by(func.count(Detection.species).desc())
                    .all()
                )

                return [{"species": row.species, "count": row.count} for row in new_species_results]
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting new species data: {e}")
                raise

    def get_most_recent_detections(self, limit: int = 10) -> list[dict]:
        """Retrieve the most recent detection records from the database."""
        with self.db_service.get_db() as db:
            try:
                recent_detections = (
                    db.query(Detection).order_by(Detection.timestamp.desc()).limit(limit).all()
                )
                return [
                    {
                        "Date": d.timestamp.strftime("%Y-%m-%d"),
                        "Time": d.timestamp.strftime("%H:%M:%S"),
                        "Sci_Name": (d.species.split(" (")[1][:-1] if " (" in d.species else ""),
                        "Com_Name": (d.species.split(" (")[0] if " (" in d.species else d.species),
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
                db.rollback()
                print(f"Error getting most recent detections: {e}")
                raise

    def get_best_detections(self, limit: int = 10) -> list[dict]:
        """Retrieve the best detection for each species, sorted by confidence."""
        with self.db_service.get_db() as db:
            try:
                # Subquery to rank detections by confidence for each species
                ranked_subquery = db.query(
                    Detection.id,
                    func.row_number()
                    .over(
                        partition_by=Detection.species,
                        order_by=Detection.confidence.desc(),
                    )
                    .label("rn"),
                ).subquery()

                # Get the IDs of the top-ranked detection for each species
                best_detection_ids_query = db.query(ranked_subquery.c.id).filter(
                    ranked_subquery.c.rn == 1
                )

                # Get the full detection objects for those IDs
                best_detections = (
                    db.query(Detection)
                    .filter(Detection.id.in_(best_detection_ids_query))
                    .order_by(Detection.confidence.desc())
                    .limit(limit)
                    .all()
                )

                return [
                    {
                        "Date": d.timestamp.strftime("%Y-%m-%d"),
                        "Time": d.timestamp.strftime("%H:%M:%S"),
                        "Sci_Name": (d.species.split(" (")[1][:-1] if " (" in d.species else ""),
                        "Com_Name": (d.species.split(" (")[0] if " (" in d.species else d.species),
                        "Confidence": d.confidence,
                        "Lat": d.latitude,
                        "Lon": d.longitude,
                        "Cutoff": d.cutoff,
                        "Week": d.week,
                        "Sens": d.sensitivity,
                        "Overlap": d.overlap,
                    }
                    for d in best_detections
                ]
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error getting best detections: {e}")
                raise

    def get_detection(self, detection_id: int) -> Detection:
        """Retrieve a single detection record from the database."""
        with self.db_service.get_db() as db:
            try:
                return db.query(Detection).get(detection_id)
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error retrieving detection: {e}")
                raise

    def update_detection_extracted_status(self, detection_id: int, is_extracted: bool) -> None:
        """Update the extracted status of a detection record in the database."""
        with self.db_service.get_db() as db:
            try:
                detection = db.query(Detection).filter_by(id=detection_id).first()
                if detection:
                    detection.is_extracted = is_extracted
                    db.commit()
                    print(f"Detection {detection_id} extracted status: {is_extracted}.")
                else:
                    print(f"Detection with ID {detection_id} not found.")
            except SQLAlchemyError as e:
                db.rollback()
                print(f"Error updating detection extracted status: {e}")
                raise
