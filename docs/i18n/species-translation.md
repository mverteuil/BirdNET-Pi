# Species Name Translation System

## Architecture Overview

The BirdNET-Pi species name translation system provides multilingual bird name support through the `MultilingualDatabaseService`. This service integrates three specialized databases to deliver comprehensive species name translations with intelligent fallback mechanisms.

### Core Components

```
MultilingualDatabaseService
├── IOC World Bird List (Primary Authority)
├── PatLevin BirdNET Labels (BirdNET-Specific)
├── Avibase (Lepage 2018) (Comprehensive Coverage)
└── SQLite ATTACH DATABASE Integration
```

## Database Hierarchy and Precedence

The system implements a three-tier precedence hierarchy designed to provide the most accurate and authoritative translations:

### 1. IOC World Bird List (Highest Priority)
- **Authority**: Official taxonomic standard
- **Coverage**: English names in species table, multilingual translations in separate table
- **Use Case**: Primary source for scientifically accurate names
- **Tables**: `species` (English), `translations` (other languages)

### 2. PatLevin BirdNET Labels (Medium Priority)
- **Authority**: BirdNET-specific translations by Patrick Levin
- **Coverage**: Optimized for BirdNET model output
- **Use Case**: Translations specifically aligned with BirdNET detection labels
- **Tables**: `patlevin_labels`

### 3. Avibase (Lowest Priority)
- **Authority**: Comprehensive multilingual bird database (Lepage 2018)
- **Coverage**: Extensive language coverage across global bird species
- **Use Case**: Fallback for comprehensive multilingual support
- **Tables**: `avibase_names`

## Technical Implementation

### Database Attachment Strategy

The service uses SQLite's `ATTACH DATABASE` feature for efficient cross-database queries:

```python
def attach_all_to_session(self, session: Session) -> None:
    """Attach all available databases to session for cross-database queries."""
    if "ioc" in self.databases_available and self.ioc_db_path:
        session.execute(text(f"ATTACH DATABASE '{self.ioc_db_path}' AS ioc"))

    if "avibase" in self.databases_available and self.avibase_db_path:
        session.execute(text(f"ATTACH DATABASE '{self.avibase_db_path}' AS avibase"))

    if "patlevin" in self.databases_available and self.patlevin_db_path:
        session.execute(text(f"ATTACH DATABASE '{self.patlevin_db_path}' AS patlevin"))
```

**Benefits of ATTACH DATABASE:**
- Single query across multiple databases
- Atomic transactions
- Consistent connection pooling
- Reduced I/O overhead

### COALESCE Query Implementation

The precedence system is implemented using SQL's `COALESCE` function, which returns the first non-NULL value from the ordered list:

```sql
SELECT
    COALESCE(
        ioc_species.english_name,     -- IOC English (highest priority)
        ioc_trans.common_name,        -- IOC translations
        patlevin.common_name,         -- PatLevin BirdNET labels
        avibase.common_name           -- Avibase (fallback)
    ) as common_name,
    CASE
        WHEN ioc_species.english_name IS NOT NULL THEN 'IOC'
        WHEN ioc_trans.common_name IS NOT NULL THEN 'IOC'
        WHEN patlevin.common_name IS NOT NULL THEN 'PatLevin'
        WHEN avibase.common_name IS NOT NULL THEN 'Avibase'
        ELSE NULL
    END as source
FROM (SELECT 1 as dummy) base
LEFT JOIN ioc.species ioc_species
    ON LOWER(ioc_species.scientific_name) = LOWER(:sci_name)
LEFT JOIN ioc.translations ioc_trans
    ON LOWER(ioc_trans.scientific_name) = LOWER(:sci_name)
    AND ioc_trans.language_code = :lang
LEFT JOIN patlevin.patlevin_labels patlevin
    ON LOWER(patlevin.scientific_name) = LOWER(:sci_name)
    AND patlevin.language_code = :lang
LEFT JOIN avibase.avibase_names avibase
    ON LOWER(avibase.scientific_name) = LOWER(:sci_name)
    AND avibase.language_code = :lang
```

### Query Optimization Features

**Case-Insensitive Matching**: All scientific name comparisons use `LOWER()` functions to ensure reliable matching regardless of case variations in input data.

**Parameterized Queries**: All user inputs are passed as parameters (`:sci_name`, `:lang`) to prevent SQL injection attacks.

**Conditional Joins**: The service dynamically builds queries including only available databases, reducing unnecessary joins.

## Database Schema Overview

### IOC World Bird List
```sql
-- Species table (English names only)
CREATE TABLE species (
    id INTEGER PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    english_name TEXT,
    -- additional taxonomic fields...
);

-- Translations table (multilingual)
CREATE TABLE translations (
    id INTEGER PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    language_code TEXT NOT NULL,
    common_name TEXT NOT NULL
);
```

### PatLevin BirdNET Labels
```sql
CREATE TABLE patlevin_labels (
    id INTEGER PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    language_code TEXT NOT NULL,
    common_name TEXT NOT NULL
);
```

### Avibase
```sql
CREATE TABLE avibase_names (
    id INTEGER PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    language_code TEXT NOT NULL,
    common_name TEXT NOT NULL
);
```

## Integration with Detection System

The MultilingualDatabaseService integrates seamlessly with BirdNET-Pi's main detection database:

```python
# Example integration in detection processing
def process_detection_with_translation(detection, language_code="en"):
    with get_database_session() as session:
        # Attach multilingual databases
        multilingual_service.attach_all_to_session(session)

        try:
            # Get best translation for detected species
            translation = multilingual_service.get_best_common_name(
                session,
                detection.scientific_name,
                language_code
            )

            detection.common_name = translation["common_name"]
            detection.name_source = translation["source"]

        finally:
            # Clean up database attachments
            multilingual_service.detach_all_from_session(session)
```

## Performance Considerations

### Efficient Resource Management

**Database Attachment Lifecycle**:
1. Attach databases only when needed
2. Execute multilingual queries
3. Detach databases to prevent resource leaks

**Query Performance**:
- Indexed scientific names in all databases
- LEFT JOIN optimization for missing databases
- Single query execution per translation request

### Memory Usage

- Databases remain on disk; only query results are loaded into memory
- SQLite's efficient B-tree indexes minimize I/O operations
- Automatic cleanup prevents connection pool exhaustion

### Error Handling

```python
def detach_all_from_session(self, session: Session) -> None:
    """Detach all databases from session."""
    for db_alias in ["ioc", "avibase", "patlevin"]:
        if db_alias in self.databases_available:
            try:
                session.execute(text(f"DETACH DATABASE {db_alias}"))
            except Exception:
                # Ignore errors if database wasn't attached
                pass
```

**Graceful Degradation**: The system continues to function even if some databases are unavailable, providing translation from remaining sources.

**Exception Safety**: Database detachment operations never fail the overall process, ensuring system stability.

## Code Examples

### Basic Translation Lookup

```python
from birdnetpi.services.multilingual_database_service import MultilingualDatabaseService

# Initialize service
multilingual_service = MultilingualDatabaseService(file_resolver)

# Get best available translation
with session as db_session:
    multilingual_service.attach_all_to_session(db_session)

    try:
        result = multilingual_service.get_best_common_name(
            db_session,
            scientific_name="Turdus migratorius",
            language_code="es"
        )

        print(f"Name: {result['common_name']}")  # "Petirrojo Americano"
        print(f"Source: {result['source']}")     # "IOC"

    finally:
        multilingual_service.detach_all_from_session(db_session)
```

### Comprehensive Translation Retrieval

```python
# Get all available translations for a species
translations = multilingual_service.get_all_translations(
    db_session,
    "Turdus migratorius"
)

# Results structure:
# {
#     "en": [{"name": "American Robin", "source": "IOC"}],
#     "es": [
#         {"name": "Petirrojo Americano", "source": "IOC"},
#         {"name": "Petirrojo", "source": "PatLevin"}
#     ],
#     "fr": [{"name": "Merle d'Amérique", "source": "IOC"}],
#     "de": [{"name": "Wanderdrossel", "source": "PatLevin"}]
# }
```

### Attribution Management

```python
# Get proper attribution strings for legal compliance
attributions = multilingual_service.get_attribution()

# Example output:
# [
#     "IOC World Bird List (www.worldbirdnames.org)",
#     "Patrick Levin (patlevin) - BirdNET Label Translations",
#     "Avibase - Lepage, Denis (2018)"
# ]
```

## Development Best Practices

### Database Management
1. Always attach databases at the start of translation operations
2. Use try/finally blocks to ensure proper detachment
3. Handle missing databases gracefully
4. Test with partial database availability scenarios

### Query Construction
1. Use parameterized queries for all user inputs
2. Implement case-insensitive matching for scientific names
3. Build queries dynamically based on available databases
4. Include source attribution in query results

### Error Handling
1. Implement graceful degradation for missing databases
2. Handle database attachment/detachment errors without failing
3. Provide meaningful error messages for debugging
4. Test edge cases like empty inputs and special characters

### Testing Strategies
1. Unit test each query building method independently
2. Integration test with real SQLite databases
3. Test all database availability combinations
4. Verify SQL injection prevention
5. Performance test with large datasets
