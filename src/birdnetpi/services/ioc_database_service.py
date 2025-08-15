"""Lightweight service for IOC database queries.

This service provides simple, efficient queries to the IOC World Bird Names database.
For complex multilingual queries with fallback priorities, use MultilingualDatabaseService.
"""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from birdnetpi.models.ioc_database_models import IOCSpecies
from birdnetpi.models.ioc_species_core import IOCSpeciesCore


class IOCDatabaseService:
    """Lightweight service for IOC database queries."""

    def __init__(self, db_path: Path | str):
        """Initialize IOC database service.

        Args:
            db_path: Path to IOC SQLite database
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"IOC database not found: {self.db_path}")

        # Create read-only connection
        self.engine = create_engine(
            f"sqlite:///{self.db_path}?mode=ro", connect_args={"check_same_thread": False}
        )
        self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_species_core(self, scientific_name: str) -> IOCSpeciesCore | None:
        """Get minimal species data by scientific name.

        This lightweight query returns only the essential fields actually used by the
        application, reducing memory usage and improving performance.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOCSpeciesCore with essential fields or None if not found
        """
        with self.session_local() as session:
            result = (
                session.query(
                    IOCSpecies.scientific_name,
                    IOCSpecies.english_name,
                    IOCSpecies.order_name,
                    IOCSpecies.family,
                    IOCSpecies.genus,
                    IOCSpecies.species_epithet,
                    IOCSpecies.authority,
                )
                .filter_by(scientific_name=scientific_name)
                .first()
            )

            if result:
                return IOCSpeciesCore(
                    scientific_name=result[0],
                    english_name=result[1],
                    order_name=result[2],
                    family=result[3],
                    genus=result[4],
                    species_epithet=result[5],
                    authority=result[6],
                )
            return None

    def get_english_name(self, scientific_name: str) -> str | None:
        """Get IOC canonical English common name.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOC English common name or None if not found
        """
        with self.session_local() as session:
            result = (
                session.query(IOCSpecies.english_name)
                .filter_by(scientific_name=scientific_name)
                .scalar()
            )
            return result

    def species_exists(self, scientific_name: str) -> bool:
        """Check if a species exists in the IOC database.

        Args:
            scientific_name: Scientific name to check

        Returns:
            True if species exists, False otherwise
        """
        with self.session_local() as session:
            count = session.query(IOCSpecies).filter_by(scientific_name=scientific_name).count()
            return count > 0

    def get_species_count(self) -> int:
        """Get total number of species in the database.

        Returns:
            Number of species
        """
        with self.session_local() as session:
            return session.query(IOCSpecies).count()

    def get_metadata_value(self, key: str) -> str | None:
        """Get a specific metadata value.

        Args:
            key: Metadata key (e.g., 'ioc_version', 'species_count')

        Returns:
            Metadata value or None if not found
        """
        with self.session_local() as session:
            result = session.execute(
                text("SELECT value FROM metadata WHERE key = :key"), {"key": key}
            ).scalar()
            return result
