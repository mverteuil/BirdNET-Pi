"""Service for managing multilingual bird name databases.

This service provides access to three bird name databases:
1. IOC World Bird List (authoritative taxonomy)
2. Avibase (Lepage 2018, extensive multilingual coverage)
3. PatLevin BirdNET labels (BirdNET-specific translations)

Uses SQLite's ATTACH DATABASE for efficient cross-database queries with priority:
IOC → PatLevin → Avibase
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from birdnetpi.system.path_resolver import PathResolver


class SpeciesDatabaseService:
    """Service for multilingual bird name lookups across three databases."""

    def __init__(self, path_resolver: PathResolver):
        """Initialize multilingual database service.

        Args:
            path_resolver: File path resolver for database locations
        """
        self.path_resolver = path_resolver
        self.ioc_db_path = path_resolver.get_ioc_database_path()
        self.avibase_db_path = path_resolver.get_avibase_database_path()
        self.patlevin_db_path = path_resolver.get_patlevin_database_path()

        # All three databases are always present - the asset downloader ensures this
        # No need for fallback support

    async def attach_all_to_session(self, session: AsyncSession) -> None:
        """Attach all databases to session for cross-database queries.

        Args:
            session: SQLAlchemy async session (typically from main detections database)
        """
        # Always attach all three databases - they're guaranteed to exist
        await session.execute(text(f"ATTACH DATABASE '{self.ioc_db_path}' AS ioc"))
        await session.execute(text(f"ATTACH DATABASE '{self.avibase_db_path}' AS avibase"))
        await session.execute(text(f"ATTACH DATABASE '{self.patlevin_db_path}' AS patlevin"))

    async def detach_all_from_session(self, session: AsyncSession) -> None:
        """Detach all databases from session.

        Args:
            session: SQLAlchemy async session
        """
        # Detach all three databases
        for db_alias in ["ioc", "avibase", "patlevin"]:
            try:
                await session.execute(text(f"DETACH DATABASE {db_alias}"))
            except Exception:
                # Ignore errors if database wasn't attached (shouldn't happen)
                pass

    async def get_best_common_name(
        self, session: AsyncSession, scientific_name: str, language_code: str = "en"
    ) -> dict[str, Any]:
        """Get best available common name using priority: IOC → PatLevin → Avibase.

        Args:
            session: SQLAlchemy async session with databases attached
            scientific_name: Scientific name to look up
            language_code: Language code for translation (default: en)

        Returns:
            Dictionary with common_name, source, and metadata
        """
        # Priority order: IOC English (for en) → IOC translation → PatLevin → Avibase

        # Try IOC English name first (for English only)
        if language_code == "en":
            stmt = text("""
                SELECT english_name
                FROM ioc.species
                WHERE LOWER(scientific_name) = LOWER(:sci_name)
            """)
            result = await session.execute(stmt, {"sci_name": scientific_name})
            row = result.first()
            if row and row.english_name:  # type: ignore[attr-defined]
                return {"common_name": row.english_name, "source": "IOC"}  # type: ignore[attr-defined]

        # Try IOC translations
        stmt = text("""
            SELECT common_name
            FROM ioc.translations
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
            AND language_code = :lang
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name, "lang": language_code})
        row = result.first()
        if row and row.common_name:  # type: ignore[attr-defined]
            return {"common_name": row.common_name, "source": "IOC"}  # type: ignore[attr-defined]

        # Try PatLevin
        stmt = text("""
            SELECT common_name
            FROM patlevin.patlevin_labels
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
            AND language_code = :lang
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name, "lang": language_code})
        row = result.first()
        if row and row.common_name:  # type: ignore[attr-defined]
            return {"common_name": row.common_name, "source": "PatLevin"}  # type: ignore[attr-defined]

        # Try Avibase
        stmt = text("""
            SELECT common_name
            FROM avibase.avibase_names
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
            AND language_code = :lang
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name, "lang": language_code})
        row = result.first()
        if row and row.common_name:  # type: ignore[attr-defined]
            return {"common_name": row.common_name, "source": "Avibase"}  # type: ignore[attr-defined]

        # No match found
        return {"common_name": None, "source": None}

    async def get_all_translations(
        self, session: AsyncSession, scientific_name: str
    ) -> dict[str, list[dict[str, str]]]:
        """Get all available translations from all databases.

        Args:
            session: SQLAlchemy async session with databases attached
            scientific_name: Scientific name to look up

        Returns:
            Dictionary with language codes as keys, list of {name, source} as values
        """
        translations = {}

        # Get from IOC
        # English from species table
        stmt = text("""
            SELECT english_name
            FROM ioc.species
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name})
        row = result.first()
        if row and row.english_name:  # type: ignore[attr-defined]
            translations.setdefault("en", []).append({"name": row.english_name, "source": "IOC"})  # type: ignore[attr-defined]

        # Other languages from translations table
        stmt = text("""
            SELECT language_code, common_name
            FROM ioc.translations
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name})
        for row in result:
            if row.language_code and row.common_name:  # type: ignore[attr-defined]
                translations.setdefault(row.language_code, []).append(  # type: ignore[attr-defined]
                    {"name": row.common_name, "source": "IOC"}  # type: ignore[attr-defined]
                )

        # Get from PatLevin
        stmt = text("""
            SELECT language_code, common_name
            FROM patlevin.patlevin_labels
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name})
        for row in result:
            if row.language_code and row.common_name:  # type: ignore[attr-defined]
                # Check if not duplicate
                existing_names = [t["name"] for t in translations.get(row.language_code, [])]  # type: ignore[attr-defined]
                if row.common_name not in existing_names:  # type: ignore[attr-defined]
                    translations.setdefault(row.language_code, []).append(  # type: ignore[attr-defined]
                        {"name": row.common_name, "source": "PatLevin"}  # type: ignore[attr-defined]
                    )

        # Get from Avibase
        stmt = text("""
            SELECT language_code, common_name
            FROM avibase.avibase_names
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name})
        for row in result:
            if row.language_code and row.common_name:  # type: ignore[attr-defined]
                # Check if not duplicate
                existing_names = [t["name"] for t in translations.get(row.language_code, [])]  # type: ignore[attr-defined]
                if row.common_name not in existing_names:  # type: ignore[attr-defined]
                    translations.setdefault(row.language_code, []).append(  # type: ignore[attr-defined]
                        {"name": row.common_name, "source": "Avibase"}  # type: ignore[attr-defined]
                    )

        return translations

    def get_attribution(self) -> list[str]:
        """Get attribution strings for all databases.

        Returns:
            List of attribution strings
        """
        # Always return attributions for all three databases
        return [
            "IOC World Bird List (www.worldbirdnames.org)",
            "Patrick Levin (patlevin) - BirdNET Label Translations",
            "Avibase - Lepage, Denis (2018)",
        ]
