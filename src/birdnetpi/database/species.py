"""Service for managing multilingual bird name databases.

This service provides access to two bird name databases:
1. IOC World Bird List (authoritative taxonomy, 24 languages)
2. Wikidata (extensive multilingual coverage, 57 languages, plus images and conservation status)

Uses SQLite's ATTACH DATABASE for efficient cross-database queries with priority:
IOC → Wikidata

All lookups use avibase_id as the primary key with indexed scientific_name for efficient lookup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from birdnetpi.system.path_resolver import PathResolver


class SpeciesDatabaseService:
    """Service for multilingual bird name lookups across two databases."""

    def __init__(self, path_resolver: PathResolver):
        """Initialize species database service.

        Args:
            path_resolver: File path resolver for database locations
        """
        self.path_resolver = path_resolver
        self.ioc_db_path = path_resolver.get_ioc_database_path()
        self.wikidata_db_path = path_resolver.get_wikidata_database_path()

        # Both databases are always present - the asset downloader ensures this
        # No need for fallback support

    async def attach_all_to_session(self, session: AsyncSession) -> None:
        """Attach all databases to session for cross-database queries.

        Args:
            session: SQLAlchemy async session (typically from main detections database)
        """
        # Always attach both databases - they're guaranteed to exist
        # Safe: paths come from PathResolver, not user input
        ioc_sql = text(f"ATTACH DATABASE '{self.ioc_db_path}' AS ioc")  # nosemgrep
        await session.execute(ioc_sql)
        wikidata_sql = text(f"ATTACH DATABASE '{self.wikidata_db_path}' AS wikidata")  # nosemgrep
        await session.execute(wikidata_sql)

    async def detach_all_from_session(self, session: AsyncSession) -> None:
        """Detach all databases from session.

        Args:
            session: SQLAlchemy async session
        """
        # Detach both databases
        for db_alias in ["ioc", "wikidata"]:
            try:
                # Safe: database aliases are from hardcoded list, not user input
                await session.execute(text(f"DETACH DATABASE {db_alias}"))  # nosemgrep
            except Exception:
                # Ignore errors if database wasn't attached (shouldn't happen)
                pass

    async def get_best_common_name(
        self, session: AsyncSession, scientific_name: str, language_code: str = "en"
    ) -> dict[str, Any]:
        """Get best available common name using priority: IOC → Wikidata.

        Lookup pattern:
        1. Get avibase_id from scientific_name (using UNIQUE INDEX for speed)
        2. For English: try IOC english_name first
        3. Try IOC translations
        4. Try Wikidata translations

        Args:
            session: SQLAlchemy async session with databases attached
            scientific_name: Scientific name to look up
            language_code: Language code for translation (default: en)

        Returns:
            Dictionary with common_name, source, and metadata
        """
        # Step 1: Get avibase_id from scientific_name (uses UNIQUE INDEX for O(log n) lookup)
        stmt = text("""
            SELECT avibase_id
            FROM ioc.species
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name})
        row = result.first()

        if not row:
            # No match found for this scientific name
            return {"common_name": None, "source": None}

        avibase_id = row.avibase_id  # type: ignore[attr-defined]

        # Step 2: Try IOC English name first (for English only)
        if language_code == "en":
            stmt = text("""
                SELECT english_name
                FROM ioc.species
                WHERE avibase_id = :avibase_id
            """)
            result = await session.execute(stmt, {"avibase_id": avibase_id})
            row = result.first()
            if row and row.english_name:  # type: ignore[attr-defined]
                return {"common_name": row.english_name, "source": "IOC"}  # type: ignore[attr-defined]

        # Step 3: Try IOC translations
        stmt = text("""
            SELECT common_name
            FROM ioc.translations
            WHERE avibase_id = :avibase_id
            AND language_code = :lang
        """)
        result = await session.execute(stmt, {"avibase_id": avibase_id, "lang": language_code})
        row = result.first()
        if row and row.common_name:  # type: ignore[attr-defined]
            return {"common_name": row.common_name, "source": "IOC"}  # type: ignore[attr-defined]

        # Step 4: Try Wikidata
        stmt = text("""
            SELECT common_name
            FROM wikidata.translations
            WHERE avibase_id = :avibase_id
            AND language_code = :lang
        """)
        result = await session.execute(stmt, {"avibase_id": avibase_id, "lang": language_code})
        row = result.first()
        if row and row.common_name:  # type: ignore[attr-defined]
            return {"common_name": row.common_name, "source": "Wikidata"}  # type: ignore[attr-defined]

        # No translation found for this language
        return {"common_name": None, "source": None}

    async def get_all_translations(
        self, session: AsyncSession, scientific_name: str
    ) -> dict[str, list[dict[str, str]]]:
        """Get all available translations from all databases.

        Uses avibase_id for efficient lookup across databases.

        Args:
            session: SQLAlchemy async session with databases attached
            scientific_name: Scientific name to look up

        Returns:
            Dictionary with language codes as keys, list of {name, source} as values
        """
        translations = {}

        # Step 1: Get avibase_id and English name from scientific_name
        stmt = text("""
            SELECT avibase_id, english_name
            FROM ioc.species
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name})
        row = result.first()

        if not row:
            # No match found for this scientific name
            return translations

        avibase_id = row.avibase_id  # type: ignore[attr-defined]

        # Add English name if present
        if row.english_name:  # type: ignore[attr-defined]
            translations.setdefault("en", []).append({"name": row.english_name, "source": "IOC"})  # type: ignore[attr-defined]

        # Step 2: Other languages from IOC translations table
        stmt = text("""
            SELECT language_code, common_name
            FROM ioc.translations
            WHERE avibase_id = :avibase_id
        """)
        result = await session.execute(stmt, {"avibase_id": avibase_id})
        for row in result:
            if row.language_code and row.common_name:  # type: ignore[attr-defined]
                # Check if not duplicate (same deduplication as Wikidata)
                existing_names = [t["name"] for t in translations.get(row.language_code, [])]  # type: ignore[attr-defined]
                if row.common_name not in existing_names:  # type: ignore[attr-defined]
                    translations.setdefault(row.language_code, []).append(  # type: ignore[attr-defined]
                        {"name": row.common_name, "source": "IOC"}  # type: ignore[attr-defined]
                    )

        # Step 3: Get from Wikidata
        stmt = text("""
            SELECT language_code, common_name
            FROM wikidata.translations
            WHERE avibase_id = :avibase_id
        """)
        result = await session.execute(stmt, {"avibase_id": avibase_id})
        for row in result:
            if row.language_code and row.common_name:  # type: ignore[attr-defined]
                # Check if not duplicate
                existing_names = [t["name"] for t in translations.get(row.language_code, [])]  # type: ignore[attr-defined]
                if row.common_name not in existing_names:  # type: ignore[attr-defined]
                    translations.setdefault(row.language_code, []).append(  # type: ignore[attr-defined]
                        {"name": row.common_name, "source": "Wikidata"}  # type: ignore[attr-defined]
                    )

        return translations

    def get_attribution(self) -> list[str]:
        """Get attribution strings for all databases.

        Returns:
            List of attribution strings
        """
        # Always return attributions for both databases
        return [
            "IOC World Bird List (www.worldbirdnames.org) - CC-BY-4.0",
            "Wikidata - Public Domain (CC0)",
        ]

    async def get_species_taxonomy(
        self, session: AsyncSession, scientific_name: str
    ) -> dict[str, str] | None:
        """Get taxonomic information for a species.

        Args:
            session: SQLAlchemy async session with databases attached
            scientific_name: Scientific name to look up

        Returns:
            Dictionary with order, family, genus, or None if not found
        """
        # Query IOC database for taxonomy
        # The IOC database has order_name and family columns in the species table
        stmt = text("""
            SELECT order_name, family
            FROM ioc.species
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """)
        result = await session.execute(stmt, {"sci_name": scientific_name})
        row = result.first()

        if not row:
            return None

        # Extract genus from scientific name (first word)
        genus = scientific_name.split()[0] if scientific_name else ""

        return {
            "order": row.order_name if hasattr(row, "order_name") else "",  # type: ignore[attr-defined]
            "family": row.family if hasattr(row, "family") else "",  # type: ignore[attr-defined]
            "genus": genus,
        }
