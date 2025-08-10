# MultilingualDatabaseService API Reference

## Overview

The `MultilingualDatabaseService` provides programmatic access to multilingual bird species name translations through a priority-based system using three specialized databases. This API reference covers all public methods, parameters, return values, and usage patterns.

## Class Definition

```python
from birdnetpi.services.multilingual_database_service import MultilingualDatabaseService
```

### Constructor

```python
def __init__(self, file_resolver: FilePathResolver) -> None
```

**Description**: Initializes the multilingual database service and detects available databases.

**Parameters**:
- `file_resolver` (`FilePathResolver`): File path resolver for locating database files

**Behavior**:
- Automatically detects which translation databases are available
- Stores database paths for IOC, Avibase, and PatLevin databases
- Populates `databases_available` list with detected databases

**Example**:
```python
from birdnetpi.utils.file_path_resolver import FilePathResolver

file_resolver = FilePathResolver()
service = MultilingualDatabaseService(file_resolver)

# Check which databases were detected
print(f"Available databases: {service.databases_available}")
# Output: ['ioc', 'patlevin', 'avibase'] (if all are present)
```

## Database Management Methods

### attach_all_to_session()

```python
def attach_all_to_session(self, session: Session) -> None
```

**Description**: Attaches all available translation databases to a SQLAlchemy session for cross-database queries.

**Parameters**:
- `session` (`Session`): SQLAlchemy session, typically from the main detections database

**Returns**: `None`

**Side Effects**:
- Executes `ATTACH DATABASE` statements for each available database
- Databases become queryable as `ioc.*`, `avibase.*`, `patlevin.*`

**Raises**:
- `OperationalError`: If database files are corrupted or inaccessible
- `SQLAlchemyError`: For other database connection issues

**Usage Pattern**:
```python
with get_database_session() as session:
    service.attach_all_to_session(session)
    try:
        # Perform multilingual queries
        result = service.get_best_common_name(session, "Turdus migratorius", "es")
    finally:
        service.detach_all_from_session(session)
```

**Important**: Always pair with `detach_all_from_session()` to prevent resource leaks.

### detach_all_from_session()

```python
def detach_all_from_session(self, session: Session) -> None
```

**Description**: Detaches all translation databases from the session.

**Parameters**:
- `session` (`Session`): SQLAlchemy session with attached databases

**Returns**: `None`

**Error Handling**: Gracefully handles detachment errors without raising exceptions, ensuring cleanup always succeeds.

**Example**:
```python
try:
    service.attach_all_to_session(session)
    # ... perform queries ...
finally:
    service.detach_all_from_session(session)  # Always succeeds
```

## Translation Query Methods

### get_best_common_name()

```python
def get_best_common_name(
    self,
    session: Session,
    scientific_name: str,
    language_code: str = "en"
) -> dict[str, Any]
```

**Description**: Retrieves the best available common name using database precedence: IOC → PatLevin → Avibase.

**Parameters**:
- `session` (`Session`): SQLAlchemy session with databases attached
- `scientific_name` (`str`): Scientific name to translate (e.g., "Turdus migratorius")
- `language_code` (`str`, optional): Target language code (default: "en")

**Returns**: `dict[str, Any]` with keys:
- `common_name` (`str | None`): Translated common name, or `None` if not found
- `source` (`str | None`): Database source ("IOC", "PatLevin", "Avibase"), or `None` if not found

**Query Logic**:
1. For English (`en`): Checks IOC species table first, then IOC translations, then PatLevin, then Avibase
2. For other languages: Checks IOC translations, then PatLevin, then Avibase
3. Returns first non-NULL result based on precedence

**Examples**:

```python
# English translation (highest priority from IOC species table)
result = service.get_best_common_name(session, "Turdus migratorius", "en")
print(result)
# {"common_name": "American Robin", "source": "IOC"}

# Spanish translation (from IOC translations table)
result = service.get_best_common_name(session, "Turdus migratorius", "es")
print(result)
# {"common_name": "Petirrojo Americano", "source": "IOC"}

# Language with limited coverage (fallback to Avibase)
result = service.get_best_common_name(session, "Turdus migratorius", "hi")
print(result)
# {"common_name": "अमेरिकी रॉबिन", "source": "Avibase"}

# Species not found
result = service.get_best_common_name(session, "Nonexistent species", "en")
print(result)
# {"common_name": None, "source": None}
```

**Error Handling**:
- Raises `SQLAlchemyError` for database connection or query issues
- Uses parameterized queries to prevent SQL injection
- Case-insensitive scientific name matching via `LOWER()` function

### get_all_translations()

```python
def get_all_translations(
    self,
    session: Session,
    scientific_name: str
) -> dict[str, list[dict[str, str]]]
```

**Description**: Retrieves all available translations from all databases, organized by language.

**Parameters**:
- `session` (`Session`): SQLAlchemy session with databases attached
- `scientific_name` (`str`): Scientific name to look up

**Returns**: `dict[str, list[dict[str, str]]]` where:
- Keys are language codes (`str`)
- Values are lists of translation objects with keys:
  - `name` (`str`): The translated common name
  - `source` (`str`): Database source ("IOC", "PatLevin", "Avibase")

**Behavior**:
- Queries all databases for the given species
- Deduplicates identical names within each language
- Preserves multiple different names from different sources
- Returns empty dict if species not found in any database

**Example**:
```python
translations = service.get_all_translations(session, "Turdus migratorius")
print(translations)

# Output:
{
    "en": [
        {"name": "American Robin", "source": "IOC"},
        {"name": "American Robin", "source": "PatLevin"},  # If different from IOC
        {"name": "Robin", "source": "Avibase"}            # Alternative name
    ],
    "es": [
        {"name": "Petirrojo Americano", "source": "IOC"},
        {"name": "Petirrojo", "source": "PatLevin"}
    ],
    "fr": [
        {"name": "Merle d'Amérique", "source": "IOC"}
    ],
    "de": [
        {"name": "Wanderdrossel", "source": "PatLevin"}
    ]
}

# Species not found
translations = service.get_all_translations(session, "Nonexistent species")
print(translations)
# {}
```

**Use Cases**:
- Displaying all available name variants
- Language coverage analysis
- Translation quality comparison
- Database coverage assessment

## Utility Methods

### get_attribution()

```python
def get_attribution(self) -> list[str]
```

**Description**: Returns proper attribution strings for all available databases, for legal compliance and acknowledgment.

**Parameters**: None

**Returns**: `list[str]` - List of attribution strings

**Example**:
```python
attributions = service.get_attribution()
print(attributions)

# Output (when all databases available):
[
    "IOC World Bird List (www.worldbirdnames.org)",
    "Patrick Levin (patlevin) - BirdNET Label Translations",
    "Avibase - Lepage, Denis (2018)"
]

# Output (when only IOC and PatLevin available):
[
    "IOC World Bird List (www.worldbirdnames.org)",
    "Patrick Levin (patlevin) - BirdNET Label Translations"
]

# Output (when no databases available):
[]
```

**Usage**: Include these attribution strings in user interfaces, reports, or documentation that display translated species names.

## Properties

### databases_available

```python
@property
databases_available: list[str]
```

**Description**: Read-only list of available database identifiers.

**Returns**: `list[str]` containing subset of `["ioc", "patlevin", "avibase"]`

**Example**:
```python
print(service.databases_available)
# ["ioc", "patlevin", "avibase"] (all available)
# ["ioc", "patlevin"]            (avibase missing)
# []                             (no databases found)
```

### Database Path Properties

```python
ioc_db_path: str | None
avibase_db_path: str | None
patlevin_db_path: str | None
```

**Description**: File paths to individual database files, or `None` if not available.

**Example**:
```python
print(f"IOC database: {service.ioc_db_path}")
print(f"Avibase database: {service.avibase_db_path}")
print(f"PatLevin database: {service.patlevin_db_path}")
```

## Complete Usage Examples

### Basic Translation Workflow

```python
from sqlalchemy.orm import sessionmaker
from birdnetpi.services.multilingual_database_service import MultilingualDatabaseService

# Initialize service
file_resolver = FilePathResolver()
multilingual_service = MultilingualDatabaseService(file_resolver)

# Create database session
session_factory = sessionmaker(bind=engine)

def translate_species(scientific_name: str, language_code: str = "en") -> dict:
    """Translate a species name with proper resource management."""
    with session_factory() as session:
        multilingual_service.attach_all_to_session(session)

        try:
            result = multilingual_service.get_best_common_name(
                session,
                scientific_name,
                language_code
            )
            return result
        finally:
            multilingual_service.detach_all_from_session(session)

# Usage
translation = translate_species("Turdus migratorius", "es")
print(f"Spanish name: {translation['common_name']}")  # "Petirrojo Americano"
print(f"Source: {translation['source']}")             # "IOC"
```

### Batch Translation Processing

```python
def translate_species_list(species_list: list[str], language_code: str) -> list[dict]:
    """Efficiently translate multiple species by reusing database session."""
    results = []

    with session_factory() as session:
        multilingual_service.attach_all_to_session(session)

        try:
            for scientific_name in species_list:
                result = multilingual_service.get_best_common_name(
                    session,
                    scientific_name,
                    language_code
                )
                results.append({
                    "scientific_name": scientific_name,
                    "common_name": result["common_name"],
                    "source": result["source"]
                })
        finally:
            multilingual_service.detach_all_from_session(session)

    return results

# Usage
species = ["Turdus migratorius", "Passer domesticus", "Corvus brachyrhynchos"]
translations = translate_species_list(species, "de")

for t in translations:
    print(f"{t['scientific_name']} → {t['common_name']} ({t['source']})")
```

### Comprehensive Translation Analysis

```python
def analyze_species_coverage(scientific_name: str) -> dict:
    """Analyze translation coverage across all databases and languages."""
    with session_factory() as session:
        multilingual_service.attach_all_to_session(session)

        try:
            # Get all translations
            all_translations = multilingual_service.get_all_translations(
                session,
                scientific_name
            )

            # Get attribution info
            attributions = multilingual_service.get_attribution()

            # Analyze coverage
            analysis = {
                "scientific_name": scientific_name,
                "total_languages": len(all_translations),
                "translations_by_language": all_translations,
                "available_databases": multilingual_service.databases_available,
                "attributions": attributions
            }

            # Count translations per database
            source_counts = {}
            for lang_translations in all_translations.values():
                for translation in lang_translations:
                    source = translation["source"]
                    source_counts[source] = source_counts.get(source, 0) + 1

            analysis["translations_per_database"] = source_counts
            return analysis

        finally:
            multilingual_service.detach_all_from_session(session)

# Usage
coverage = analyze_species_coverage("Turdus migratorius")
print(f"Available in {coverage['total_languages']} languages")
print(f"Database contributions: {coverage['translations_per_database']}")
```

## Error Handling Patterns

### Graceful Degradation

```python
def get_species_name_with_fallback(scientific_name: str, language_code: str) -> str:
    """Get species name with graceful fallback to scientific name."""
    try:
        with session_factory() as session:
            multilingual_service.attach_all_to_session(session)

            try:
                result = multilingual_service.get_best_common_name(
                    session,
                    scientific_name,
                    language_code
                )

                # Return translated name or fallback to scientific name
                return result["common_name"] or scientific_name

            finally:
                multilingual_service.detach_all_from_session(session)

    except Exception as e:
        # Log error and return scientific name as ultimate fallback
        logger.error(f"Translation failed for {scientific_name}: {e}")
        return scientific_name
```

### Database Availability Checking

```python
def ensure_translation_databases() -> bool:
    """Check if translation databases are available."""
    file_resolver = FilePathResolver()
    service = MultilingualDatabaseService(file_resolver)

    if not service.databases_available:
        logger.warning("No translation databases available")
        return False

    logger.info(f"Available databases: {service.databases_available}")
    return True

# Usage
if ensure_translation_databases():
    # Proceed with translation operations
    pass
else:
    # Handle missing databases (show English names only, etc.)
    pass
```

## Performance Considerations

### Connection Management

- **Attach/Detach Overhead**: Database attachment has minimal overhead but should be paired properly
- **Session Reuse**: Reuse sessions for batch operations to avoid repeated attachment
- **Connection Pooling**: SQLAlchemy's connection pooling works with attached databases

### Query Optimization

- **Single Query Execution**: Each translation requires only one SQL query
- **Index Usage**: All databases have indexes on scientific names for fast lookups
- **Parameterized Queries**: Prevent SQL parsing overhead and injection attacks

### Memory Usage

- **Minimal Memory Footprint**: Only query results are loaded into memory
- **No Database Caching**: Databases remain on disk; SQLite handles caching
- **Automatic Cleanup**: Database detachment releases all associated resources

## Integration Patterns

### Web API Integration

```python
from flask import Flask, request, jsonify

app = Flask(__name__)
multilingual_service = MultilingualDatabaseService(file_resolver)

@app.route('/api/translate')
def translate_species():
    scientific_name = request.args.get('scientific_name')
    language_code = request.args.get('language', 'en')

    if not scientific_name:
        return jsonify({"error": "scientific_name parameter required"}), 400

    try:
        with session_factory() as session:
            multilingual_service.attach_all_to_session(session)

            try:
                result = multilingual_service.get_best_common_name(
                    session,
                    scientific_name,
                    language_code
                )
                return jsonify(result)

            finally:
                multilingual_service.detach_all_from_session(session)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### Background Task Integration

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def translate_detection_batch(detections: list, language_code: str):
    """Asynchronously translate a batch of detections."""
    loop = asyncio.get_event_loop()

    with ThreadPoolExecutor() as executor:
        def translate_batch():
            results = []
            with session_factory() as session:
                multilingual_service.attach_all_to_session(session)

                try:
                    for detection in detections:
                        result = multilingual_service.get_best_common_name(
                            session,
                            detection.scientific_name,
                            language_code
                        )
                        detection.common_name = result["common_name"]
                        detection.translation_source = result["source"]
                        results.append(detection)
                finally:
                    multilingual_service.detach_all_from_session(session)

            return results

        return await loop.run_in_executor(executor, translate_batch)
```

This comprehensive API reference provides all the information needed to integrate and use the MultilingualDatabaseService effectively in various contexts, from simple translations to complex multilingual applications.
