"""Service for managing IOC reference database operations.

This service handles creation, population, and querying of the IOC reference database
which is separate from the main detections database but can be joined using
SQLite's ATTACH DATABASE functionality.
"""

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from birdnetpi.models.ioc_database_models import (
    IOCBase,
    IOCLanguage,
    IOCMetadata,
    IOCSpecies,
    IOCTranslation,
)
from birdnetpi.services.ioc_reference_service import IOCReferenceService


class IOCDatabaseService:
    """Service for IOC reference database operations."""

    def __init__(self, db_path: str):
        """Initialize IOC database service.

        Args:
            db_path: Path to IOC reference SQLite database
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        IOCBase.metadata.create_all(self.engine)
        self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Auto-upgrade existing databases with performance indexes
        self._ensure_performance_indexes()

    def populate_from_ioc_service(self, ioc_service: IOCReferenceService) -> None:
        """Populate database from IOCReferenceService data with optimizations.

        Args:
            ioc_service: Loaded IOC reference service with data
        """
        if not ioc_service._loaded:
            raise ValueError("IOC service must be loaded before populating database")

        session = self.session_local()
        try:
            # Optimize SQLite settings for bulk insert
            session.execute(text("PRAGMA journal_mode = OFF"))
            session.execute(text("PRAGMA synchronous = OFF"))
            session.execute(text("PRAGMA temp_store = MEMORY"))
            session.execute(text("PRAGMA mmap_size = 268435456"))  # 256MB

            # Clear existing data
            session.query(IOCTranslation).delete()
            session.query(IOCSpecies).delete()
            session.query(IOCLanguage).delete()
            session.query(IOCMetadata).delete()
            session.commit()

            # Prepare bulk insert data
            species_data = []
            species_count = 0
            for _scientific_name, species_info in ioc_service._species_data.items():
                species_data.append(
                    {
                        "scientific_name": species_info.scientific_name,
                        "english_name": species_info.english_name,
                        "order_name": species_info.order,
                        "family": species_info.family,
                        "genus": species_info.genus,
                        "species_epithet": species_info.species,
                        "authority": species_info.authority,
                        "breeding_regions": species_info.breeding_regions,
                        "breeding_subregions": species_info.breeding_subregions,
                    }
                )
                species_count += 1

            # Bulk insert species
            session.bulk_insert_mappings(IOCSpecies, species_data)  # type: ignore[arg-type]
            session.commit()
            print(f"Inserted {species_count} species total")

            # Prepare bulk insert for translations
            translation_data = []
            translation_count = 0
            language_counts: dict[str, int] = {}

            for scientific_name, translations in ioc_service._translations.items():
                for language_code, common_name in translations.items():
                    translation_data.append(
                        {
                            "scientific_name": scientific_name,
                            "language_code": language_code,
                            "common_name": common_name,
                        }
                    )
                    translation_count += 1
                    language_counts[language_code] = language_counts.get(language_code, 0) + 1

            # Bulk insert translations
            session.bulk_insert_mappings(IOCTranslation, translation_data)  # type: ignore[arg-type]
            session.commit()
            print(f"Inserted {translation_count} translations total")

            # Insert language metadata
            language_names = self._get_language_names()
            for language_code, count in language_counts.items():
                language_name = language_names.get(language_code, language_code.upper())
                db_language = IOCLanguage(
                    language_code=language_code,
                    language_name=language_name,
                    translation_count=count,
                )
                session.add(db_language)

            # Insert metadata
            metadata_entries = [
                IOCMetadata(key="ioc_version", value=ioc_service.get_ioc_version()),
                IOCMetadata(key="created_at", value=datetime.utcnow().isoformat()),
                IOCMetadata(key="species_count", value=str(species_count)),
                IOCMetadata(key="translation_count", value=str(translation_count)),
                IOCMetadata(
                    key="languages_available", value=",".join(sorted(language_counts.keys()))
                ),
            ]

            for metadata in metadata_entries:
                session.add(metadata)

            session.commit()
            print(
                f"IOC database populated successfully: {species_count} species, "
                f"{translation_count} translations"
            )

            # Create performance indexes for JOIN operations
            self._create_performance_indexes()

        except Exception as e:
            session.rollback()
            raise RuntimeError(f"Failed to populate IOC database: {e}") from e
        finally:
            session.close()

    def _create_performance_indexes(self) -> None:
        """Create database indexes for optimal JOIN performance.

        This method creates indexes on the IOC database tables to optimize
        queries used by DetectionQueryService. Since the IOC database is
        populated from external sources, we need to add these indexes
        programmatically after population.
        """
        session = self.session_local()
        try:
            print("Creating performance indexes for IOC database...")

            # Indexes for species table (taxonomy-based queries)
            session.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_species_family
                ON species(family)
            """)
            )

            session.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_species_genus
                ON species(genus)
            """)
            )

            session.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_species_order_family
                ON species(order_name, family)
            """)
            )

            session.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_species_english_name
                ON species(english_name)
            """)
            )

            # Critical indexes for translations table (JOIN performance)
            session.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_translations_scientific_language
                ON translations(scientific_name, language_code)
            """)
            )

            session.execute(
                text("""
                CREATE INDEX IF NOT EXISTS idx_translations_language_common
                ON translations(language_code, common_name)
            """)
            )

            session.commit()
            print("Performance indexes created successfully")

        except Exception as e:
            session.rollback()
            raise RuntimeError(f"Failed to create performance indexes: {e}") from e
        finally:
            session.close()

    def create_performance_indexes(self) -> None:
        """Public method to create performance indexes on existing IOC database.

        This can be called to add indexes to IOC databases that were created
        before the performance optimization feature was implemented.
        """
        self._create_performance_indexes()

    def _ensure_performance_indexes(self) -> None:
        """Ensure performance indexes exist, creating them if missing.

        This method is called during service initialization to automatically
        upgrade existing IOC databases that may lack performance indexes.
        """
        if not os.path.exists(self.db_path):
            return  # No database file exists yet

        if not self._has_data():
            return  # Empty database, indexes will be created when populated

        if self._indexes_exist():
            return  # Indexes already present

        print("Upgrading IOC database with performance indexes...")
        self._create_performance_indexes()

    def _has_data(self) -> bool:
        """Check if IOC database has been populated with data."""
        session = self.session_local()
        try:
            # Check if species table has any data
            result = session.execute(text("SELECT COUNT(*) FROM species")).scalar()
            return (result or 0) > 0
        except Exception:
            # Table might not exist or other DB error
            return False
        finally:
            session.close()

    def _indexes_exist(self) -> bool:
        """Check if performance indexes already exist in the database."""
        session = self.session_local()
        try:
            # Check for the key composite index on translations table
            result = session.execute(
                text("""
                SELECT name FROM sqlite_master
                WHERE type='index'
                AND name='idx_translations_scientific_language'
            """)
            ).fetchone()
            return result is not None
        except Exception:
            return False
        finally:
            session.close()

    def _get_language_names(self) -> dict[str, str]:
        """Get mapping of language codes to display names."""
        return {
            "ca": "Catalan",
            "zh": "Chinese",
            "zh-TW": "Chinese (Traditional)",
            "hr": "Croatian",
            "cs": "Czech",
            "da": "Danish",
            "nl": "Dutch",
            "fi": "Finnish",
            "fr": "French",
            "de": "German",
            "it": "Italian",
            "ja": "Japanese",
            "lt": "Lithuanian",
            "no": "Norwegian",
            "pl": "Polish",
            "pt": "Portuguese",
            "pt-PT": "Portuguese (Portuguese)",
            "ru": "Russian",
            "sr": "Serbian",
            "sk": "Slovak",
            "es": "Spanish",
            "sv": "Swedish",
            "tr": "Turkish",
            "uk": "Ukrainian",
            "af": "Afrikaans",
            "ar": "Arabic",
            "be": "Belarusian",
            "bg": "Bulgarian",
            "et": "Estonian",
            "fr-Gaudin": "French (Gaudin)",
            "el": "Greek",
            "he": "Hebrew",
            "hu": "Hungarian",
            "is": "Icelandic",
            "id": "Indonesian",
            "ko": "Korean",
            "lv": "Latvian",
            "mk": "Macedonian",
            "ml": "Malayalam",
            "se": "Northern Sami",
            "fa": "Persian",
            "ro": "Romanian",
            "sl": "Slovenian",
            "th": "Thai",
        }

    def get_species_by_scientific_name(self, scientific_name: str) -> IOCSpecies | None:
        """Get species by scientific name.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOCSpecies object or None if not found
        """
        session = self.session_local()
        try:
            return session.query(IOCSpecies).filter_by(scientific_name=scientific_name).first()
        finally:
            session.close()

    def get_translation(self, scientific_name: str, language_code: str) -> str | None:
        """Get translated common name for species and language.

        Args:
            scientific_name: Scientific name to lookup
            language_code: Language code (e.g., 'es', 'fr')

        Returns:
            Translated common name or None if not found
        """
        session = self.session_local()
        try:
            translation = (
                session.query(IOCTranslation)
                .filter_by(scientific_name=scientific_name, language_code=language_code)
                .first()
            )
            if translation is not None:
                common_name = getattr(translation, "common_name", None)
                return str(common_name) if common_name else None
            return None
        finally:
            session.close()

    def search_species_by_common_name(
        self, common_name: str, language_code: str = "en", limit: int = 10
    ) -> list[IOCSpecies]:
        """Search species by common name (partial match).

        Args:
            common_name: Common name to search for
            language_code: Language to search in
            limit: Maximum results to return

        Returns:
            List of matching IOCSpecies objects
        """
        session = self.session_local()
        try:
            search_term = f"%{common_name.lower()}%"

            if language_code == "en":
                # Search English names directly in species table
                return (
                    session.query(IOCSpecies)
                    .filter(IOCSpecies.english_name.ilike(search_term))
                    .limit(limit)
                    .all()
                )
            else:
                # Search translations and join with species
                return (
                    session.query(IOCSpecies)
                    .join(IOCTranslation)
                    .filter(
                        IOCTranslation.language_code == language_code,
                        IOCTranslation.common_name.ilike(search_term),
                    )
                    .limit(limit)
                    .all()
                )
        finally:
            session.close()

    def get_available_languages(self) -> list[IOCLanguage]:
        """Get all available languages with translation counts.

        Returns:
            List of IOCLanguage objects
        """
        session = self.session_local()
        try:
            return session.query(IOCLanguage).order_by(IOCLanguage.language_code).all()
        finally:
            session.close()

    def get_metadata(self) -> dict[str, str]:
        """Get all metadata key-value pairs.

        Returns:
            Dictionary of metadata
        """
        session = self.session_local()
        try:
            metadata_list = session.query(IOCMetadata).all()
            return {str(item.key): str(item.value) for item in metadata_list}
        finally:
            session.close()

    def get_database_size(self) -> int:
        """Get database file size in bytes.

        Returns:
            Database file size in bytes
        """
        return os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0

    def attach_to_session(self, session: Session, alias: str = "ioc") -> None:
        """Attach IOC database to an existing session for cross-database queries.

        Args:
            session: SQLAlchemy session (typically from main detections database)
            alias: Alias for the attached database (default: 'ioc')

        Example:
            # In your main database service
            with main_db.get_db() as session:
                ioc_db.attach_to_session(session, 'ioc')

                # Now you can query across databases
                result = session.execute(text('''
                    SELECT d.species, d.confidence, s.english_name, t.common_name
                    FROM detections d
                    LEFT JOIN ioc.species s ON d.scientific_name = s.scientific_name
                    LEFT JOIN ioc.translations t ON s.scientific_name = t.scientific_name
                        AND t.language_code = :lang
                    WHERE d.timestamp > :since
                '''), {'lang': 'es', 'since': '2024-01-01'})
        """
        attach_sql = text(f"ATTACH DATABASE '{self.db_path}' AS {alias}")
        session.execute(attach_sql)

    def detach_from_session(self, session: Session, alias: str = "ioc") -> None:
        """Detach IOC database from session.

        Args:
            session: SQLAlchemy session
            alias: Alias of the attached database
        """
        detach_sql = text(f"DETACH DATABASE {alias}")
        session.execute(detach_sql)


def create_ioc_database_from_files(
    xml_file: Path, xlsx_file: Path, db_path: str
) -> IOCDatabaseService:
    """Create IOC reference database from IOC XML and XLSX files.

    Args:
        xml_file: Path to IOC XML file
        xlsx_file: Path to IOC multilingual XLSX file
        db_path: Path for output SQLite database

    Returns:
        Configured IOCDatabaseService
    """
    # Load data using IOC reference service
    ioc_service = IOCReferenceService()
    ioc_service.load_ioc_data(xml_file=xml_file, xlsx_file=xlsx_file)

    # Create and populate database
    db_service = IOCDatabaseService(db_path)
    db_service.populate_from_ioc_service(ioc_service)

    return db_service
