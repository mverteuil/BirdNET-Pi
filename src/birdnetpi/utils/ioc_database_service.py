"""Lightweight service for IOC database queries.

This service provides simple, efficient queries to the IOC World Bird Names database.
For complex multilingual queries with fallback priorities, use MultilingualDatabaseService.
"""

from pathlib import Path

from sqlalchemy import create_engine, exists, func, select, text
from sqlalchemy.orm import sessionmaker

from birdnetpi.species.models import Species
from birdnetpi.utils.ioc_models import IOCSpecies


class IOCDatabaseService:
    """Lightweight service for IOC database queries."""

    def __init__(self, db_path: Path):
        """Initialize IOC database service.

        Args:
            db_path: Path to IOC SQLite database
        """
        self.db_path = db_path
        if not self.db_path.exists():
            raise FileNotFoundError(f"IOC database not found: {self.db_path}")

        # Create read-only connection
        self.engine = create_engine(
            f"sqlite:///{self.db_path}?mode=ro", connect_args={"check_same_thread": False}
        )
        self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_species_core(self, scientific_name: str) -> Species | None:
        """Get minimal species data by scientific name.

        This lightweight query returns only the essential fields actually used by the
        application, reducing memory usage and improving performance.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOCSpeciesCore with essential fields or None if not found
        """
        with self.session_local() as session:
            stmt = select(IOCSpecies).where(IOCSpecies.scientific_name == scientific_name)
            species = session.execute(stmt).scalar_one_or_none()

            if species:
                return Species(
                    scientific_name=species.scientific_name,
                    english_name=species.english_name,
                    order_name=species.order_name,
                    family=species.family,
                    genus=species.genus,
                    species_epithet=species.species_epithet,
                    authority=species.authority,
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
            stmt = select(IOCSpecies.english_name).where(
                IOCSpecies.scientific_name == scientific_name
            )
            result = session.execute(stmt).scalar()
            return result

    def species_exists(self, scientific_name: str) -> bool:
        """Check if a species exists in the IOC database.

        Args:
            scientific_name: Scientific name to check

        Returns:
            True if species exists, False otherwise
        """
        with self.session_local() as session:
            stmt = select(exists().where(IOCSpecies.scientific_name == scientific_name))
            result = session.execute(stmt).scalar()
            return bool(result)

    def get_species_count(self) -> int:
        """Get total number of species in the database.

        Returns:
            Number of species
        """
        with self.session_local() as session:
            stmt = select(func.count()).select_from(IOCSpecies)
            count = session.execute(stmt).scalar()
            return count or 0

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
