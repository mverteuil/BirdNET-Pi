"""Lightweight service for IOC database queries.

This service provides simple, efficient queries to the IOC World Bird Names database.
For complex multilingual queries with fallback priorities, use MultilingualDatabaseService.
"""

from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from birdnetpi.database.ioc.ioc_database_models import IOCSpecies
from birdnetpi.species.ioc_species_core import IOCSpeciesCore


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
            stmt = select(
                IOCSpecies.scientific_name,
                IOCSpecies.english_name,
                IOCSpecies.order_name,
                IOCSpecies.family,
                IOCSpecies.genus,
                IOCSpecies.species_epithet,
                IOCSpecies.authority,
            ).where(IOCSpecies.scientific_name == scientific_name)
            result = session.execute(stmt).first()

            if result:
                return IOCSpeciesCore(
                    scientific_name=result[0],  # type: ignore[arg-type]
                    english_name=result[1],  # type: ignore[arg-type]
                    order_name=result[2],  # type: ignore[arg-type]
                    family=result[3],  # type: ignore[arg-type]
                    genus=result[4],  # type: ignore[arg-type]
                    species_epithet=result[5],  # type: ignore[arg-type]
                    authority=result[6],  # type: ignore[arg-type]
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
            stmt = (
                select(func.count())
                .select_from(IOCSpecies)
                .where(IOCSpecies.scientific_name == scientific_name)
            )
            count = session.execute(stmt).scalar()
            return count > 0  # type: ignore[operator]

    def get_species_count(self) -> int:
        """Get total number of species in the database.

        Returns:
            Number of species
        """
        with self.session_local() as session:
            stmt = select(func.count()).select_from(IOCSpecies)
            return session.execute(stmt).scalar()  # type: ignore[return-value]

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
