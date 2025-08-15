"""IOC World Bird Names database builder and reference provider.

This utility combines XML/XLSX processing with SQLite database creation for
IOC (International Ornithological Committee) World Bird Names data.

The utility handles:
1. Loading IOC XML taxonomy data
2. Processing multilingual XLSX translations
3. Creating optimized SQLite databases
4. Providing runtime lookups and data export
"""

import contextlib
import json
import os
import xml.etree.ElementTree as ET
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from birdnetpi.models.ioc_database_models import (
    IOCBase,
    IOCLanguage,
    IOCMetadata,
    IOCSpecies,
    IOCTranslation,
)
from birdnetpi.models.ioc_species_core import IOCSpeciesCore


@dataclass
class IOCSpeciesData:
    """IOC species data structure."""

    scientific_name: str  # Primary key - full "Genus species"
    english_name: str  # IOC canonical English common name
    order: str  # Taxonomic order
    family: str  # Taxonomic family
    genus: str  # Genus name
    species: str  # Species epithet
    authority: str  # Scientific authority
    breeding_regions: str | None = None
    breeding_subregions: str | None = None


@dataclass
class IOCTranslationData:
    """IOC species translation data."""

    scientific_name: str  # Reference to IOCSpeciesData
    language_code: str  # ISO language code
    common_name: str  # Translated common name


class IOCDatabaseBuilder:
    """Builder for IOC World Bird Names reference databases."""

    def __init__(self, data_dir: Path | None = None, db_path: Path | str | None = None):
        """Initialize IOC database builder.

        Args:
            data_dir: Directory containing IOC data files (for XML/XLSX loading)
            db_path: Path to SQLite database (for database operations)
        """
        self.data_dir = data_dir or Path(".")
        self._species_data: dict[str, IOCSpeciesData] = {}
        self._translations: dict[str, dict[str, str]] = {}  # {scientific_name: {lang: translation}}
        self._ioc_version = "unknown"
        self._loaded = False

        # Database-related attributes
        self.db_path: Path | None = None
        self.engine = None
        self.session_local = None

        if db_path:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(f"sqlite:///{self.db_path}")
            IOCBase.metadata.create_all(self.engine)
            self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

            # Auto-upgrade existing databases with performance indexes
            self._ensure_performance_indexes()

    # ==================== XML/XLSX Loading Methods ====================

    def load_ioc_data(
        self,
        xml_file: Path | None = None,
        xlsx_file: Path | None = None,
        force_reload: bool = False,
    ) -> None:
        """Load IOC data from XML and XLSX files.

        Args:
            xml_file: Path to IOC XML file (auto-detects if None)
            xlsx_file: Path to IOC multilingual XLSX file (auto-detects if None)
            force_reload: Force reload even if already loaded
        """
        if self._loaded and not force_reload:
            return

        # Auto-detect files if not provided
        if xml_file is None:
            xml_file = self._find_ioc_xml_file()
        if xlsx_file is None:
            xlsx_file = self._find_ioc_xlsx_file()

        if xml_file and xml_file.exists():
            self._load_xml_data(xml_file)

        if xlsx_file and xlsx_file.exists():
            self._load_xlsx_translations(xlsx_file)

        self._loaded = True

    def _find_ioc_xml_file(self) -> Path | None:
        """Find IOC XML file in data directory."""
        patterns = ["*ioc*names*.xml", "*IOC*.xml", "master_ioc-names_xml*.xml"]
        for pattern in patterns:
            files = list(self.data_dir.glob(pattern))
            if files:
                return files[0]  # Return first match
        return None

    def _find_ioc_xlsx_file(self) -> Path | None:
        """Find IOC multilingual XLSX file in data directory."""
        patterns = ["*multiling*IOC*.xlsx", "*Multiling*IOC*.xlsx", "*multilingual*.xlsx"]
        for pattern in patterns:
            files = list(self.data_dir.glob(pattern))
            if files:
                return files[0]  # Return first match
        return None

    def _load_xml_data(self, xml_file: Path) -> None:
        """Load species data from IOC XML file with version-tolerant parsing.

        Args:
            xml_file: Path to IOC XML file
        """
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()

            # Extract version from root element (version-tolerant)
            self._ioc_version = root.get("version", "unknown")

            # Parse species data using XPath patterns that work across versions
            species_count = 0
            for order_elem in root.findall(".//order"):
                order_name = self._get_element_text(order_elem, "latin_name", "")

                for family_elem in order_elem.findall(".//family"):
                    family_latin = self._get_element_text(family_elem, "latin_name", "")

                    for genus_elem in family_elem.findall(".//genus"):
                        genus_name = self._get_element_text(genus_elem, "latin_name", "")
                        genus_authority = self._get_element_text(genus_elem, "authority", "")

                        for species_elem in genus_elem.findall("species"):
                            species_epithet = self._get_element_text(species_elem, "latin_name", "")
                            species_authority = self._get_element_text(
                                species_elem, "authority", ""
                            )
                            english_name = self._get_element_text(species_elem, "english_name", "")
                            breeding_regions = self._get_element_text(
                                species_elem, "breeding_regions", ""
                            )
                            breeding_subregions = self._get_element_text(
                                species_elem, "breeding_subregions", ""
                            )

                            # TODO: Detect and skip extinct species
                            # IOC marks extinct species with daggers:
                            # - Single dagger (†) for species described from live specimens
                            # - Double dagger (††) for species described from subfossils
                            # Need to check actual XML format to see if:
                            # 1. Dagger is in english_name (e.g., "†Passenger Pigeon")
                            # 2. There's an extinct="true" attribute
                            # 3. There's a separate <extinct> element
                            # For now, including all species until we can verify the format

                            if genus_name and species_epithet and english_name:
                                scientific_name = f"{genus_name} {species_epithet}"

                                # Use species-level authority if available, otherwise genus
                                authority = species_authority or genus_authority

                                species_data = IOCSpeciesData(
                                    scientific_name=scientific_name,
                                    english_name=english_name,
                                    order=order_name,
                                    family=family_latin,
                                    genus=genus_name,
                                    species=species_epithet,
                                    authority=authority,
                                    breeding_regions=breeding_regions,
                                    breeding_subregions=breeding_subregions,
                                )

                                self._species_data[scientific_name] = species_data
                                species_count += 1

            print(f"Loaded {species_count} species from IOC XML v{self._ioc_version}")

        except ET.ParseError as e:
            raise ValueError(f"Failed to parse IOC XML file {xml_file}: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to load IOC XML data from {xml_file}: {e}") from e

    def _get_element_text(self, parent: ET.Element, tag_name: str, default: str) -> str:
        """Get text from child element with fallback.

        Args:
            parent: Parent XML element
            tag_name: Child element tag name
            default: Default value if element not found

        Returns:
            Element text or default value
        """
        elem = parent.find(tag_name)
        return elem.text.strip() if elem is not None and elem.text else default

    def _load_xlsx_translations(self, xlsx_file: Path) -> None:  # noqa: C901
        """Load multilingual translations from IOC XLSX file.

        Args:
            xlsx_file: Path to IOC multilingual XLSX file
        """
        try:
            wb = openpyxl.load_workbook(xlsx_file)
            ws = wb.active

            # Get headers (first row)
            if ws is None:
                raise ValueError("Worksheet is None - cannot process XLSX file")

            headers = [str(cell.value) if cell.value is not None else "" for cell in ws[1]]

            # Map language columns (skip seq, Order, Family, IOC_15.1, English)
            lang_columns = {}
            for i, header in enumerate(headers):
                if header and header not in ["seq", "Order", "Family", "IOC_15.1", "English"]:
                    # Map language names to codes
                    lang_code = self._map_language_to_code(str(header))
                    if lang_code:
                        lang_columns[lang_code] = i

            # Process data rows
            translation_count = 0
            if ws.max_row:
                for row in range(2, ws.max_row + 1):  # Skip header row
                    values = [cell.value for cell in ws[row]]

                    # IOC_15.1 column contains the scientific name
                    ioc_col_idx = headers.index("IOC_15.1") if "IOC_15.1" in headers else None
                    if ioc_col_idx is None or not values[ioc_col_idx]:
                        continue

                    scientific_name = str(values[ioc_col_idx]).strip()

                    # Initialize translations dict for this species
                    if scientific_name not in self._translations:
                        self._translations[scientific_name] = {}

                    # Extract translations for each language
                    for lang_code, col_idx in lang_columns.items():
                        if col_idx < len(values) and values[col_idx]:
                            translated_name = str(values[col_idx]).strip()
                            if translated_name:
                                self._translations[scientific_name][lang_code] = translated_name
                                translation_count += 1

            print(f"Loaded {translation_count} translations for {len(self._translations)} species")

        except Exception as e:
            raise ValueError(f"Failed to load IOC XLSX translations from {xlsx_file}: {e}") from e

    def _map_language_to_code(self, language_name: str) -> str | None:
        """Map language display name to ISO language code.

        Args:
            language_name: Language display name from XLSX header

        Returns:
            ISO language code or None if not recognized
        """
        # Language mapping from IOC XLSX headers to ISO codes
        language_map = {
            "Catalan": "ca",
            "Chinese": "zh",
            "Chinese (Traditional)": "zh-TW",
            "Croatian": "hr",
            "Czech": "cs",
            "Danish": "da",
            "Dutch": "nl",
            "Finnish": "fi",
            "French": "fr",
            "German": "de",
            "Italian": "it",
            "Japanese": "ja",
            "Lithuanian": "lt",
            "Norwegian": "no",
            "Polish": "pl",
            "Portuguese (Lusophone)": "pt",
            "Portuguese (Portuguese)": "pt-PT",
            "Russian": "ru",
            "Serbian": "sr",
            "Slovak": "sk",
            "Spanish": "es",
            "Swedish": "sv",
            "Turkish": "tr",
            "Ukrainian": "uk",
            "Afrikaans": "af",
            "Arabic": "ar",
            "Belarusian": "be",
            "Bulgarian": "bg",
            "Estonian": "et",
            "French (Gaudin)": "fr-Gaudin",
            "Greek": "el",
            "Hebrew": "he",
            "Hungarian": "hu",
            "Icelandic": "is",
            "Indonesian": "id",
            "Korean": "ko",
            "Latvian": "lv",
            "Macedonian": "mk",
            "Malayalam": "ml",
            "Northern Sami": "se",
            "Persian": "fa",
            "Romanian": "ro",
            "Slovenian": "sl",
            "Thai": "th",
        }
        return language_map.get(language_name)

    # ==================== Data Access Methods ====================

    def get_ioc_common_name(self, scientific_name: str) -> str | None:
        """Get IOC canonical English common name for scientific name.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOC English common name or None if not found
        """
        if not self._loaded:
            self.load_ioc_data()

        species = self._species_data.get(scientific_name)
        return species.english_name if species else None

    def get_translated_common_name(self, scientific_name: str, language_code: str) -> str | None:
        """Get translated common name for scientific name and language.

        Args:
            scientific_name: Scientific name to lookup
            language_code: ISO language code (e.g., 'es', 'fr', 'de')

        Returns:
            Translated common name or None if not found
        """
        if not self._loaded:
            self.load_ioc_data()

        species_translations = self._translations.get(scientific_name, {})
        return species_translations.get(language_code)

    def get_species_info(self, scientific_name: str) -> IOCSpeciesData | None:
        """Get complete IOC species information.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOCSpeciesData object or None if not found
        """
        if not self._loaded:
            self.load_ioc_data()

        return self._species_data.get(scientific_name)

    def search_species_by_common_name(
        self, common_name: str, language_code: str = "en"
    ) -> list[IOCSpeciesData]:
        """Search for species by common name (partial match).

        Args:
            common_name: Common name to search for (case insensitive)
            language_code: Language code for search (default: English)

        Returns:
            List of matching IOCSpeciesData objects
        """
        if not self._loaded:
            self.load_ioc_data()

        matches = []
        search_term = common_name.lower()

        if language_code == "en":
            # Search English names in species data
            for species in self._species_data.values():
                if search_term in species.english_name.lower():
                    matches.append(species)
        else:
            # Search translations
            for scientific_name, translations in self._translations.items():
                translated_name = translations.get(language_code, "")
                if search_term in translated_name.lower():
                    species = self._species_data.get(scientific_name)
                    if species:
                        matches.append(species)

        return matches

    def get_available_languages(self) -> set[str]:
        """Get set of available language codes for translations.

        Returns:
            Set of ISO language codes
        """
        if not self._loaded:
            self.load_ioc_data()

        languages = set()
        for translations in self._translations.values():
            languages.update(translations.keys())
        return languages

    def get_species_count(self) -> int:
        """Get total number of species in the dataset.

        Returns:
            Number of species
        """
        if not self._loaded:
            self.load_ioc_data()

        return len(self._species_data)

    def get_ioc_version(self) -> str:
        """Get IOC version string.

        Returns:
            IOC version (e.g., "15.1")
        """
        if not self._loaded:
            self.load_ioc_data()

        return self._ioc_version

    # ==================== Export Methods ====================

    def export_json(
        self, output_file: Path, include_translations: bool = True, compress: bool = False
    ) -> None:
        """Export IOC data to JSON format for caching or distribution.

        Args:
            output_file: Path to output JSON file
            include_translations: Whether to include translation data
            compress: Whether to gzip compress the output
        """
        if not self._loaded:
            self.load_ioc_data()

        data = {
            "version": self._ioc_version,
            "species_count": len(self._species_data),
            "species": {
                scientific_name: {
                    "scientific_name": species.scientific_name,
                    "english_name": species.english_name,
                    "order": species.order,
                    "family": species.family,
                    "genus": species.genus,
                    "species": species.species,
                    "authority": species.authority,
                    "breeding_regions": species.breeding_regions,
                    "breeding_subregions": species.breeding_subregions,
                }
                for scientific_name, species in self._species_data.items()
            },
        }

        if include_translations:
            data["translations"] = self._translations
            data["available_languages"] = sorted(self.get_available_languages())

        if compress:
            import gzip

            with gzip.open(output_file, "wt", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"), ensure_ascii=False)

        file_size = output_file.stat().st_size
        print(f"Exported IOC data to {output_file} ({file_size:,} bytes)")

    def load_from_json(self, json_file: Path, compressed: bool | None = None) -> None:
        """Load IOC data from previously exported JSON file.

        Args:
            json_file: Path to JSON file
            compressed: Whether file is gzip compressed (auto-detects if None)
        """
        # Auto-detect compression from file extension
        if compressed is None:
            compressed = json_file.suffix.lower() == ".gz" or str(json_file).endswith(".json.gz")

        if compressed:
            import gzip

            with gzip.open(json_file, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

        self._ioc_version = data.get("version", "unknown")
        self._species_data = {}
        self._translations = data.get("translations", {})

        # Reconstruct IOCSpeciesData objects
        for scientific_name, species_dict in data.get("species", {}).items():
            species = IOCSpeciesData(**species_dict)
            self._species_data[scientific_name] = species

        self._loaded = True
        print(f"Loaded IOC data from JSON: {len(self._species_data)} species, v{self._ioc_version}")

    # ==================== Database Methods ====================

    @contextlib.contextmanager
    def get_db(self) -> Generator[Session, Any, None]:
        """Provide a database session for dependency injection."""
        if not self.session_local:
            raise RuntimeError("Database not initialized. Provide db_path to constructor.")

        db = self.session_local()
        try:
            yield db
        finally:
            db.close()

    def populate_database(self) -> None:
        """Populate database from loaded IOC data with optimizations."""
        if not self._loaded:
            raise ValueError("IOC data must be loaded before populating database")

        if not self.session_local:
            raise RuntimeError("Database not initialized. Provide db_path to constructor.")

        with self.get_db() as session:
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
                for _scientific_name, species_info in self._species_data.items():
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

                for scientific_name, translations in self._translations.items():
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
                    IOCMetadata(key="ioc_version", value=self.get_ioc_version()),
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

    def _create_performance_indexes(self) -> None:
        """Create database indexes for optimal JOIN performance."""
        if not self.session_local:
            return

        with self.get_db() as session:
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

    def create_performance_indexes(self) -> None:
        """Public method to create performance indexes on existing IOC database."""
        self._create_performance_indexes()

    def _ensure_performance_indexes(self) -> None:
        """Ensure performance indexes exist, creating them if missing."""
        if not self.db_path or not os.path.exists(self.db_path):
            return  # No database file exists yet

        if not self._has_data():
            return  # Empty database, indexes will be created when populated

        if self._indexes_exist():
            return  # Indexes already present

        print("Upgrading IOC database with performance indexes...")
        self._create_performance_indexes()

    def _has_data(self) -> bool:
        """Check if IOC database has been populated with data."""
        if not self.session_local:
            return False

        with self.get_db() as session:
            try:
                # Check if species table has any data
                result = session.execute(text("SELECT COUNT(*) FROM species")).scalar()
                return (result or 0) > 0
            except Exception:
                # Table might not exist or other DB error
                return False

    def _indexes_exist(self) -> bool:
        """Check if performance indexes already exist in the database."""
        if not self.session_local:
            return False

        with self.get_db() as session:
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

    # ==================== Database Query Methods ====================

    def get_species_by_scientific_name(self, scientific_name: str) -> IOCSpecies | None:
        """Get species by scientific name from database.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOCSpecies object or None if not found
        """
        if not self.session_local:
            raise RuntimeError("Database not initialized. Provide db_path to constructor.")

        with self.get_db() as session:
            return session.query(IOCSpecies).filter_by(scientific_name=scientific_name).first()

    def get_species_core(self, scientific_name: str) -> IOCSpeciesCore | None:
        """Get minimal species data by scientific name from database.

        This lightweight query returns only the essential fields actually used by the
        application, reducing memory usage and improving performance.

        Args:
            scientific_name: Scientific name to lookup

        Returns:
            IOCSpeciesCore object with essential fields or None if not found
        """
        if not self.session_local:
            raise RuntimeError("Database not initialized. Provide db_path to constructor.")

        with self.get_db() as session:
            # Query only the fields we need
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
                    scientific_name=result[0],  # scientific_name
                    english_name=result[1],  # english_name
                    order_name=result[2],  # order_name
                    family=result[3],  # family
                    genus=result[4],  # genus
                    species_epithet=result[5],  # species_epithet
                    authority=result[6],  # authority
                )
            return None

    def get_translation(self, scientific_name: str, language_code: str) -> str | None:
        """Get translated common name from database.

        Args:
            scientific_name: Scientific name to lookup
            language_code: Language code (e.g., 'es', 'fr')

        Returns:
            Translated common name or None if not found
        """
        if not self.session_local:
            raise RuntimeError("Database not initialized. Provide db_path to constructor.")

        with self.get_db() as session:
            translation = (
                session.query(IOCTranslation)
                .filter_by(scientific_name=scientific_name, language_code=language_code)
                .first()
            )
            if translation is not None:
                common_name = getattr(translation, "common_name", None)
                return str(common_name) if common_name else None
            return None

    def search_species_by_common_name_db(
        self, common_name: str, language_code: str = "en", limit: int = 10
    ) -> list[IOCSpecies]:
        """Search species by common name in database (partial match).

        Args:
            common_name: Common name to search for
            language_code: Language to search in
            limit: Maximum results to return

        Returns:
            List of matching IOCSpecies objects
        """
        if not self.session_local:
            raise RuntimeError("Database not initialized. Provide db_path to constructor.")

        with self.get_db() as session:
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

    def get_available_languages_db(self) -> list[IOCLanguage]:
        """Get all available languages from database with translation counts.

        Returns:
            List of IOCLanguage objects
        """
        if not self.session_local:
            raise RuntimeError("Database not initialized. Provide db_path to constructor.")

        with self.get_db() as session:
            return session.query(IOCLanguage).order_by(IOCLanguage.language_code).all()

    def get_metadata(self) -> dict[str, str]:
        """Get all metadata key-value pairs from database.

        Returns:
            Dictionary of metadata
        """
        if not self.session_local:
            raise RuntimeError("Database not initialized. Provide db_path to constructor.")

        with self.get_db() as session:
            metadata_list = session.query(IOCMetadata).all()
            return {str(item.key): str(item.value) for item in metadata_list}

    def get_database_size(self) -> int:
        """Get database file size in bytes.

        Returns:
            Database file size in bytes
        """
        if self.db_path:
            return os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        return 0

    def attach_to_session(self, session: Session, alias: str = "ioc") -> None:
        """Attach IOC database to an existing session for cross-database queries.

        Args:
            session: SQLAlchemy session (typically from main detections database)
            alias: Alias for the attached database (default: 'ioc')

        Example:
            # In your main database service
            with main_db.get_db() as session:
                ioc_builder.attach_to_session(session, 'ioc')

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
        if not self.db_path:
            raise RuntimeError("Database path not set. Provide db_path to constructor.")

        attach_sql = text(f"ATTACH DATABASE '{self.db_path!s}' AS {alias}")
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
    xml_file: Path, xlsx_file: Path, db_path: str | Path
) -> IOCDatabaseBuilder:
    """Create IOC reference database from IOC XML and XLSX files.

    Args:
        xml_file: Path to IOC XML file
        xlsx_file: Path to IOC multilingual XLSX file
        db_path: Path for output SQLite database

    Returns:
        Configured IOCDatabaseBuilder
    """
    # Load data and create database
    builder = IOCDatabaseBuilder(db_path=Path(db_path))
    builder.load_ioc_data(xml_file=xml_file, xlsx_file=xlsx_file)
    builder.populate_database()

    return builder
