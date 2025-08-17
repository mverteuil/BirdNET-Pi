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
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from birdnetpi.utils.path_resolver import PathResolver


class MultilingualDatabaseService:
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

    def attach_all_to_session(self, session: Session) -> None:
        """Attach all databases to session for cross-database queries.

        Args:
            session: SQLAlchemy session (typically from main detections database)
        """
        # Always attach all three databases - they're guaranteed to exist
        session.execute(text(f"ATTACH DATABASE '{self.ioc_db_path}' AS ioc"))
        session.execute(text(f"ATTACH DATABASE '{self.avibase_db_path}' AS avibase"))
        session.execute(text(f"ATTACH DATABASE '{self.patlevin_db_path}' AS patlevin"))

    def detach_all_from_session(self, session: Session) -> None:
        """Detach all databases from session.

        Args:
            session: SQLAlchemy session
        """
        # Detach all three databases
        for db_alias in ["ioc", "avibase", "patlevin"]:
            try:
                session.execute(text(f"DETACH DATABASE {db_alias}"))
            except Exception:
                # Ignore errors if database wasn't attached (shouldn't happen)
                pass

    def get_best_common_name(
        self, session: Session, scientific_name: str, language_code: str = "en"
    ) -> dict[str, Any]:
        """Get best available common name using priority: IOC → PatLevin → Avibase.

        Args:
            session: SQLAlchemy session with databases attached
            scientific_name: Scientific name to look up
            language_code: Language code for translation (default: en)

        Returns:
            Dictionary with common_name, source, and metadata
        """
        select_parts, join_parts = self._build_query_parts(language_code)

        # Build and execute query (select_parts always has entries now)
        query = self._build_coalesce_query(select_parts, join_parts, language_code)

        result = session.execute(
            text(query), {"sci_name": scientific_name, "lang": language_code}
        ).fetchone()

        if result:
            return {"common_name": result[0], "source": result[1]}
        return {"common_name": None, "source": None}

    def _build_query_parts(self, language_code: str) -> tuple[list[str], list[str]]:
        """Build query parts for common name lookup.

        Args:
            language_code: Language code for translation

        Returns:
            Tuple of (select_parts, join_parts) for the query
        """
        select_parts = []
        join_parts = []

        # Always include all three databases
        self._add_ioc_query_parts(select_parts, join_parts, language_code)

        select_parts.append("patlevin.common_name")
        join_parts.append(
            """LEFT JOIN patlevin.patlevin_labels patlevin
               ON LOWER(patlevin.scientific_name) = LOWER(:sci_name)
               AND patlevin.language_code = :lang"""
        )

        select_parts.append("avibase.common_name")
        join_parts.append(
            """LEFT JOIN avibase.avibase_names avibase
               ON LOWER(avibase.scientific_name) = LOWER(:sci_name)
               AND avibase.language_code = :lang"""
        )

        return select_parts, join_parts

    def _add_ioc_query_parts(
        self, select_parts: list[str], join_parts: list[str], language_code: str
    ) -> None:
        """Add IOC database query parts to select and join lists.

        Args:
            select_parts: List to append select expressions to
            join_parts: List to append join expressions to
            language_code: Language code for translation
        """
        # IOC only has English names in the species table
        if language_code == "en":
            select_parts.append("ioc_species.english_name")
            join_parts.append(
                """LEFT JOIN ioc.species ioc_species
                   ON LOWER(ioc_species.scientific_name) = LOWER(:sci_name)"""
            )
        # IOC translations in separate table
        select_parts.append("ioc_trans.common_name")
        join_parts.append(
            """LEFT JOIN ioc.translations ioc_trans
               ON LOWER(ioc_trans.scientific_name) = LOWER(:sci_name)
               AND ioc_trans.language_code = :lang"""
        )

    def _build_coalesce_query(
        self, select_parts: list[str], join_parts: list[str], language_code: str
    ) -> str:
        """Build the final COALESCE query with source detection.

        Args:
            select_parts: List of select expressions
            join_parts: List of join expressions
            language_code: Language code for source detection

        Returns:
            Complete SQL query string
        """
        coalesce_expr = f"COALESCE({', '.join(select_parts)})"
        source_expr = self._build_source_expression(language_code)

        return f"""
            SELECT
                {coalesce_expr} as common_name,
                {source_expr} as source
            FROM (SELECT 1 as dummy) base
            {" ".join(join_parts)}
        """

    def _build_source_expression(self, language_code: str) -> str:
        """Build CASE expression for source detection.

        Args:
            language_code: Language code for IOC English name detection

        Returns:
            SQL CASE expression string
        """
        source_cases = []

        # Always include all databases in source detection
        if language_code == "en":
            source_cases.append("WHEN ioc_species.english_name IS NOT NULL THEN 'IOC'")
        source_cases.append("WHEN ioc_trans.common_name IS NOT NULL THEN 'IOC'")
        source_cases.append("WHEN patlevin.common_name IS NOT NULL THEN 'PatLevin'")
        source_cases.append("WHEN avibase.common_name IS NOT NULL THEN 'Avibase'")

        return f"CASE {' '.join(source_cases)} ELSE NULL END"

    def get_all_translations(
        self, session: Session, scientific_name: str
    ) -> dict[str, list[dict[str, str]]]:
        """Get all available translations from all databases.

        Args:
            session: SQLAlchemy session with databases attached
            scientific_name: Scientific name to look up

        Returns:
            Dictionary with language codes as keys, list of {name, source} as values
        """
        translations = {}

        # Get from IOC
        # English from species table
        query = """
            SELECT 'en' as lang, english_name as name
            FROM ioc.species
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """
        result = session.execute(text(query), {"sci_name": scientific_name}).fetchone()
        if result:
            translations.setdefault("en", []).append({"name": result[1], "source": "IOC"})

        # Other languages from translations table
        query = """
            SELECT language_code, common_name
            FROM ioc.translations
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """
        for row in session.execute(text(query), {"sci_name": scientific_name}):
            lang = row[0]
            translations.setdefault(lang, []).append({"name": row[1], "source": "IOC"})

        # Get from PatLevin
        query = """
            SELECT language_code, common_name
            FROM patlevin.patlevin_labels
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """
        for row in session.execute(text(query), {"sci_name": scientific_name}):
            lang = row[0]
            # Check if not duplicate
            existing_names = [t["name"] for t in translations.get(lang, [])]
            if row[1] not in existing_names:
                translations.setdefault(lang, []).append({"name": row[1], "source": "PatLevin"})

        # Get from Avibase
        query = """
            SELECT language_code, common_name
            FROM avibase.avibase_names
            WHERE LOWER(scientific_name) = LOWER(:sci_name)
        """
        for row in session.execute(text(query), {"sci_name": scientific_name}):
            lang = row[0]
            # Check if not duplicate
            existing_names = [t["name"] for t in translations.get(lang, [])]
            if row[1] not in existing_names:
                translations.setdefault(lang, []).append({"name": row[1], "source": "Avibase"})

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
