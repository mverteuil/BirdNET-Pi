# eBird Regional Confidence Filtering

## Overview

The eBird Regional Confidence Filtering system provides location-aware filtering of bird detections based on eBird observation data. This feature helps reduce false positives by filtering out species that are unlikely to occur in a given location at a given time of year.

The system supports three operational modes:

1. **Detection-time filtering** - Filters detections at the API endpoint before they're saved to the database
2. **Warn mode** - Logs warnings for unlikely species but still saves them to the database
3. **Admin cleanup** - Provides bulk removal tools for existing detections that don't meet regional confidence criteria

### Key Features

- **H3 Geospatial Indexing**: Uses Uber's H3 hexagonal grid system for efficient location-based lookups
- **Configurable Strictness**: Four strictness levels (vagrant, rare, uncommon, common)
- **Multiple Operational Modes**: Filter, warn, or cleanup modes
- **Regional Pack System**: Supports region-specific eBird data packs
- **Unknown Species Handling**: Configurable behavior for species not in eBird data

### Architecture

```
Detection Event → eBird Filtering → Database
                       ↓
                  EBirdRegionService
                       ↓
                  Regional Pack DB
                   (H3 + Species)
```

## Configuration

### Configuration File Structure

Add the following to your `birdnetpi.yaml` configuration:

```yaml
ebird_filtering:
  # Enable/disable the entire eBird filtering system
  enabled: true

  # Detection mode: "filter" (block), "warn" (log only), or "off"
  detection_mode: "filter"

  # Strictness level: "vagrant", "rare", "uncommon", or "common"
  # - vagrant: Block only vagrants (most permissive)
  # - rare: Block rare and vagrant species
  # - uncommon: Block uncommon, rare, and vagrant
  # - common: Allow only common species (most strict)
  detection_strictness: "vagrant"

  # Region pack name (e.g., "na-east-coast-2025.08")
  region_pack: "na-east-coast-2025.08"

  # H3 resolution level (0-15, recommended: 4-6)
  # Lower = larger cells, higher = smaller cells
  h3_resolution: 5

  # Unknown species behavior: "allow" or "block"
  # Controls what happens when species not found in eBird data
  unknown_species_behavior: "allow"
```

### Configuration Parameters

#### `enabled` (boolean)
- **Default**: `false`
- **Description**: Master switch for eBird filtering system
- **Note**: When disabled, all detections are allowed regardless of other settings

#### `detection_mode` (string)
- **Options**: `"filter"`, `"warn"`, `"off"`
- **Default**: `"filter"`
- **Description**:
  - `"filter"`: Block detections that don't meet confidence criteria
  - `"warn"`: Log warnings but allow all detections
  - `"off"`: Disable detection-time filtering (cleanup still available)

#### `detection_strictness` (string)
- **Options**: `"vagrant"`, `"rare"`, `"uncommon"`, `"common"`
- **Default**: `"vagrant"`
- **Description**: Confidence tier threshold for filtering
- **Behavior**:
  - `"vagrant"`: Block only vagrant species (rarest of the rare)
  - `"rare"`: Block rare and vagrant species
  - `"uncommon"`: Block uncommon, rare, and vagrant species
  - `"common"`: Allow only common species (most restrictive)

#### `region_pack` (string)
- **Format**: `"region-name-YYYY.MM"`
- **Example**: `"na-east-coast-2025.08"`
- **Description**: Name of the eBird regional data pack to use
- **Location**: Packs stored in `data/database/ebird_packs/`

#### `h3_resolution` (integer)
- **Range**: 0-15
- **Recommended**: 4-6
- **Default**: 5
- **Description**: H3 hexagonal grid resolution
- **Cell sizes**:
  - Resolution 4: ~34 km² hexagons
  - Resolution 5: ~4.9 km² hexagons
  - Resolution 6: ~0.7 km² hexagons

#### `unknown_species_behavior` (string)
- **Options**: `"allow"`, `"block"`
- **Default**: `"allow"`
- **Description**: How to handle species not found in eBird pack
- **Use cases**:
  - `"allow"`: Useful for hybrid/escaped/introduced species
  - `"block"`: More conservative, assumes eBird data is complete

## EBirdRegionService API Reference

### Class Definition

```python
from birdnetpi.database.ebird import EBirdRegionService
```

### Constructor

```python
def __init__(self, path_resolver: PathResolver) -> None
```

**Description**: Initializes the eBird region service.

**Parameters**:
- `path_resolver` (`PathResolver`): File path resolver for database locations

**Example**:
```python
from birdnetpi.system.path_resolver import PathResolver

path_resolver = PathResolver()
ebird_service = EBirdRegionService(path_resolver)
```

### Database Management Methods

#### attach_to_session()

```python
async def attach_to_session(
    self,
    session: AsyncSession,
    region_pack_name: str
) -> None
```

**Description**: Attaches eBird pack database to session for queries.

**Parameters**:
- `session` (`AsyncSession`): SQLAlchemy async session (from main database)
- `region_pack_name` (`str`): Name of the region pack (e.g., "na-east-coast-2025.08")

**Raises**:
- `FileNotFoundError`: If eBird pack database not found at expected path

**Usage Pattern**:
```python
async with core_db.get_async_db() as session:
    await ebird_service.attach_to_session(session, "na-east-coast-2025.08")
    try:
        # Perform eBird queries
        tier = await ebird_service.get_species_confidence_tier(
            session, "Turdus migratorius", "85283473fffffff"
        )
    finally:
        await ebird_service.detach_from_session(session)
```

**Important**: Always pair with `detach_from_session()` in a finally block.

#### detach_from_session()

```python
async def detach_from_session(self, session: AsyncSession) -> None
```

**Description**: Detaches eBird pack database from session.

**Parameters**:
- `session` (`AsyncSession`): SQLAlchemy async session

**Error Handling**: Gracefully handles detachment errors (logs but doesn't raise).

### Query Methods

#### get_species_confidence_tier()

```python
async def get_species_confidence_tier(
    self,
    session: AsyncSession,
    scientific_name: str,
    h3_cell: str,
) -> str | None
```

**Description**: Get confidence tier for a species at a specific H3 cell.

**Parameters**:
- `session` (`AsyncSession`): SQLAlchemy async session with eBird database attached
- `scientific_name` (`str`): Scientific name of the species (e.g., "Turdus migratorius")
- `h3_cell` (`str`): H3 cell index as hex string (e.g., "85283473fffffff")

**Returns**:
- `str | None`: Confidence tier ("common", "uncommon", "rare", "vagrant") or None if not found

**Examples**:

```python
# Common species in Toronto
tier = await ebird_service.get_species_confidence_tier(
    session, "Cyanocitta cristata", "85283473fffffff"
)
print(tier)  # "common"

# Vagrant species in Toronto
tier = await ebird_service.get_species_confidence_tier(
    session, "Turdus migratorius", "85283473fffffff"
)
print(tier)  # "vagrant"

# Species not in region
tier = await ebird_service.get_species_confidence_tier(
    session, "Aptenodytes forsteri", "85283473fffffff"
)
print(tier)  # None
```

**Error Handling**:
- Returns `None` for invalid H3 cell format
- Returns `None` for species not found in region

#### get_confidence_boost()

```python
async def get_confidence_boost(
    self,
    session: AsyncSession,
    scientific_name: str,
    h3_cell: str,
) -> float | None
```

**Description**: Get confidence boost multiplier for a species at a specific H3 cell.

**Parameters**:
- `session` (`AsyncSession`): SQLAlchemy async session with eBird database attached
- `scientific_name` (`str`): Scientific name of the species
- `h3_cell` (`str`): H3 cell index as hex string

**Returns**:
- `float | None`: Confidence boost multiplier (1.0-2.0) or None if not found

**Example**:
```python
# Get confidence boost for common species
boost = await ebird_service.get_confidence_boost(
    session, "Cyanocitta cristata", "85283473fffffff"
)
print(boost)  # 1.8 (hypothetical value)

# Species not in region
boost = await ebird_service.get_confidence_boost(
    session, "Nonexistent species", "85283473fffffff"
)
print(boost)  # None
```

#### is_species_in_region()

```python
async def is_species_in_region(
    self,
    session: AsyncSession,
    scientific_name: str,
    h3_cell: str,
) -> bool
```

**Description**: Check if a species is present in the eBird data for a specific H3 cell.

**Parameters**:
- `session` (`AsyncSession`): SQLAlchemy async session with eBird database attached
- `scientific_name` (`str`): Scientific name of the species
- `h3_cell` (`str`): H3 cell index as hex string

**Returns**:
- `bool`: True if species found in cell, False otherwise

**Example**:
```python
# Check if Blue Jay is in Toronto region
in_region = await ebird_service.is_species_in_region(
    session, "Cyanocitta cristata", "85283473fffffff"
)
print(in_region)  # True

# Check if Emperor Penguin is in Toronto region
in_region = await ebird_service.is_species_in_region(
    session, "Aptenodytes forsteri", "85283473fffffff"
)
print(in_region)  # False
```

#### get_allowed_species_for_location()

```python
async def get_allowed_species_for_location(
    self,
    session: AsyncSession,
    h3_cell: str,
    strictness: str,
) -> set[str]
```

**Description**: Get set of allowed species for a location based on strictness level.

**Parameters**:
- `session` (`AsyncSession`): SQLAlchemy async session with eBird database attached
- `h3_cell` (`str`): H3 cell index as hex string
- `strictness` (`str`): One of "vagrant", "rare", "uncommon", "common"

**Returns**:
- `set[str]`: Set of scientific names that pass the strictness filter

**Example**:
```python
# Get common species for Toronto
common_species = await ebird_service.get_allowed_species_for_location(
    session, "85283473fffffff", "common"
)
print(len(common_species))  # 45 (hypothetical)
print("Cyanocitta cristata" in common_species)  # True

# Get all non-vagrant species
non_vagrant = await ebird_service.get_allowed_species_for_location(
    session, "85283473fffffff", "vagrant"
)
print(len(non_vagrant))  # 234 (hypothetical)
```

**Use Case**: Site-wide filtering (currently not implemented due to performance concerns, but available for future use).

## DetectionCleanupService API Reference

### Class Definition

```python
from birdnetpi.detections.cleanup import DetectionCleanupService
```

### Constructor

```python
def __init__(
    self,
    core_database: CoreDatabaseService,
    ebird_service: EBirdRegionService,
    path_resolver: PathResolver
) -> None
```

**Description**: Initializes the detection cleanup service.

**Parameters**:
- `core_database` (`CoreDatabaseService`): Main database service
- `ebird_service` (`EBirdRegionService`): eBird region service
- `path_resolver` (`PathResolver`): File path resolver

**Example**:
```python
cleanup_service = DetectionCleanupService(
    core_database=core_db,
    ebird_service=ebird_service,
    path_resolver=path_resolver
)
```

### Data Classes

#### CleanupStats

```python
@dataclass
class CleanupStats:
    """Statistics from cleanup operation."""
    detections_evaluated: int
    detections_removed: int
    audio_files_deleted: int
    species_affected: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "detections_evaluated": self.detections_evaluated,
            "detections_removed": self.detections_removed,
            "audio_files_deleted": self.audio_files_deleted,
            "species_affected": self.species_affected,
        }
```

### Methods

#### preview_cleanup()

```python
async def preview_cleanup(
    self,
    strictness: str,
    region_pack: str,
    h3_resolution: int = 5,
    limit: int | None = None,
) -> CleanupStats
```

**Description**: Preview which detections would be removed without actually deleting them.

**Parameters**:
- `strictness` (`str`): One of "vagrant", "rare", "uncommon", "common"
- `region_pack` (`str`): Name of the region pack (e.g., "na-east-coast-2025.08")
- `h3_resolution` (`int`, optional): H3 grid resolution (default: 5)
- `limit` (`int | None`, optional): Maximum detections to evaluate (default: None = all)

**Returns**:
- `CleanupStats`: Statistics about what would be removed

**Example**:
```python
# Preview what would be removed
stats = await cleanup_service.preview_cleanup(
    strictness="vagrant",
    region_pack="na-east-coast-2025.08",
    h3_resolution=5,
    limit=100  # Evaluate first 100 detections
)

print(f"Would remove {stats.detections_removed} detections")
print(f"Evaluated {stats.detections_evaluated} detections")
print(f"Affected species: {stats.species_affected}")
```

**Use Case**: Always preview before running actual cleanup to understand the impact.

#### cleanup_detections()

```python
async def cleanup_detections(
    self,
    strictness: str,
    region_pack: str,
    h3_resolution: int = 5,
    delete_audio: bool = True,
    limit: int | None = None,
) -> CleanupStats
```

**Description**: Remove detections that don't meet regional confidence criteria.

**Parameters**:
- `strictness` (`str`): One of "vagrant", "rare", "uncommon", "common"
- `region_pack` (`str`): Name of the region pack
- `h3_resolution` (`int`, optional): H3 grid resolution (default: 5)
- `delete_audio` (`bool`, optional): Delete associated audio files (default: True)
- `limit` (`int | None`, optional): Maximum detections to process (default: None = all)

**Returns**:
- `CleanupStats`: Statistics about what was removed

**Raises**:
- `Exception`: If database operations fail (session will be rolled back)

**Example**:
```python
# Run cleanup with preview first
preview = await cleanup_service.preview_cleanup(
    strictness="vagrant",
    region_pack="na-east-coast-2025.08"
)

if preview.detections_removed < 100:
    # Safe to proceed
    stats = await cleanup_service.cleanup_detections(
        strictness="vagrant",
        region_pack="na-east-coast-2025.08",
        delete_audio=True
    )
    print(f"Removed {stats.detections_removed} detections")
    print(f"Deleted {stats.audio_files_deleted} audio files")
else:
    print("Too many detections would be removed, review configuration")
```

**Important**: This operation is irreversible. Always preview first.

## Detection Filtering Flow

### Request Flow

```
1. POST /api/detections/
2. Validate DetectionEvent payload
3. Check if eBird filtering enabled
4. If enabled:
   a. Convert lat/lon to H3 cell
   b. Attach eBird pack database
   c. Query species confidence tier
   d. Apply strictness filter
   e. Detach eBird database
5. Save or reject detection based on filter result
6. Return response
```

### Implementation

The detection filtering is implemented in `/src/birdnetpi/web/routers/detections_api_routes.py`:

```python
async def _apply_ebird_filter(
    core_database: CoreDatabaseService,
    ebird_service: EBirdRegionService,
    config: BirdNETConfig,
    scientific_name: str,
    latitude: float,
    longitude: float,
) -> tuple[bool, str]:
    """Apply eBird filtering to a detection.

    Returns:
        (should_filter, reason) tuple where:
        - should_filter: True if detection should be filtered out
        - reason: Human-readable reason for filtering decision
    """
    # Convert coordinates to H3 cell
    h3_cell = h3.latlng_to_cell(latitude, longitude, config.ebird_filtering.h3_resolution)

    # Query eBird database
    async with core_database.get_async_db() as session:
        await ebird_service.attach_to_session(session, config.ebird_filtering.region_pack)

        try:
            tier = await ebird_service.get_species_confidence_tier(
                session, scientific_name, h3_cell
            )

            # Apply filtering logic based on tier and strictness
            # ...

        finally:
            await ebird_service.detach_from_session(session)
```

### Filter Decision Logic

```python
# Unknown species handling
if tier is None:
    if unknown_species_behavior == "block":
        return (True, "Species not found in eBird data")
    else:
        return (False, "Unknown species allowed by configuration")

# Strictness-based filtering
if strictness == "vagrant" and tier == "vagrant":
    return (True, f"Vagrant species at location")
elif strictness == "rare" and tier in ["rare", "vagrant"]:
    return (True, f"{tier.capitalize()} species at location")
elif strictness == "uncommon" and tier in ["uncommon", "rare", "vagrant"]:
    return (True, f"{tier.capitalize()} species at location")
elif strictness == "common" and tier != "common":
    return (True, f"Only common species allowed, found {tier}")

# Species passes filter
return (False, f"{tier.capitalize()} species at location")
```

## Detection Cleanup API Endpoints

### Preview Cleanup

```http
POST /api/detections/cleanup/preview
Content-Type: application/json

{
  "strictness": "vagrant",
  "region_pack": "na-east-coast-2025.08",
  "h3_resolution": 5,
  "limit": 100
}
```

**Response**:
```json
{
  "detections_evaluated": 100,
  "detections_removed": 12,
  "audio_files_deleted": 0,
  "species_affected": [
    "Turdus migratorius",
    "Regulus calendula"
  ]
}
```

**Status Codes**:
- `200 OK`: Preview completed successfully
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Database or eBird service error

### Execute Cleanup

```http
POST /api/detections/cleanup/execute
Content-Type: application/json

{
  "strictness": "vagrant",
  "region_pack": "na-east-coast-2025.08",
  "h3_resolution": 5,
  "delete_audio": true,
  "limit": null
}
```

**Response**:
```json
{
  "detections_evaluated": 1234,
  "detections_removed": 56,
  "audio_files_deleted": 56,
  "species_affected": [
    "Turdus migratorius",
    "Regulus calendula",
    "Setophaga magnolia"
  ]
}
```

**Status Codes**:
- `200 OK`: Cleanup completed successfully
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Database or eBird service error

## Complete Usage Examples

### Basic Detection Filtering

```python
from fastapi import FastAPI, HTTPException
from birdnetpi.web.core.container import Container

app = FastAPI()

@app.post("/api/detections/")
async def create_detection(detection_event: DetectionEvent):
    """Create a detection with eBird filtering."""
    config = Container.config()

    # Check if filtering enabled
    if not config.ebird_filtering.enabled:
        # Save detection without filtering
        return await save_detection(detection_event)

    # Apply eBird filter
    ebird_service = Container.ebird_region_service()
    core_db = Container.core_database()

    should_filter, reason = await _apply_ebird_filter(
        core_database=core_db,
        ebird_service=ebird_service,
        config=config,
        scientific_name=detection_event.scientific_name,
        latitude=detection_event.latitude,
        longitude=detection_event.longitude,
    )

    if should_filter and config.ebird_filtering.detection_mode == "filter":
        return {
            "detection_id": None,
            "message": f"Detection filtered: {reason}"
        }
    elif should_filter and config.ebird_filtering.detection_mode == "warn":
        logger.warning(f"Unlikely detection: {reason}")
        return await save_detection(detection_event)
    else:
        return await save_detection(detection_event)
```

### Admin Cleanup Workflow

```python
async def cleanup_workflow():
    """Safe cleanup workflow with preview."""
    cleanup_service = Container.detection_cleanup_service()

    # Step 1: Preview
    print("Previewing cleanup...")
    preview = await cleanup_service.preview_cleanup(
        strictness="vagrant",
        region_pack="na-east-coast-2025.08",
        h3_resolution=5
    )

    print(f"Would remove: {preview.detections_removed} detections")
    print(f"Would evaluate: {preview.detections_evaluated} detections")
    print(f"Affected species: {preview.species_affected}")

    # Step 2: Confirm with user
    if preview.detections_removed > 100:
        print("WARNING: Large number of detections would be removed")
        confirm = input("Proceed? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cleanup cancelled")
            return

    # Step 3: Execute cleanup
    print("Executing cleanup...")
    stats = await cleanup_service.cleanup_detections(
        strictness="vagrant",
        region_pack="na-east-coast-2025.08",
        h3_resolution=5,
        delete_audio=True
    )

    print(f"Removed: {stats.detections_removed} detections")
    print(f"Deleted: {stats.audio_files_deleted} audio files")
    print(f"Success!")
```

### Batch Processing with H3

```python
import h3

async def filter_detection_batch(detections: list[Detection], config: BirdNETConfig):
    """Filter a batch of detections using eBird data."""
    ebird_service = Container.ebird_region_service()
    core_db = Container.core_database()

    filtered_detections = []

    async with core_db.get_async_db() as session:
        await ebird_service.attach_to_session(
            session, config.ebird_filtering.region_pack
        )

        try:
            for detection in detections:
                # Convert to H3 cell
                h3_cell = h3.latlng_to_cell(
                    detection.latitude,
                    detection.longitude,
                    config.ebird_filtering.h3_resolution
                )

                # Query confidence tier
                tier = await ebird_service.get_species_confidence_tier(
                    session, detection.scientific_name, h3_cell
                )

                # Apply filter logic
                if tier and tier != "vagrant":
                    filtered_detections.append(detection)

        finally:
            await ebird_service.detach_from_session(session)

    return filtered_detections
```

## Error Handling Patterns

### Graceful Degradation

```python
async def filter_with_fallback(detection_event: DetectionEvent, config: BirdNETConfig):
    """Apply eBird filter with graceful fallback."""
    try:
        should_filter, reason = await _apply_ebird_filter(
            core_database=core_db,
            ebird_service=ebird_service,
            config=config,
            scientific_name=detection_event.scientific_name,
            latitude=detection_event.latitude,
            longitude=detection_event.longitude,
        )
        return should_filter, reason
    except FileNotFoundError:
        logger.error("eBird pack not found, allowing detection")
        return False, "eBird pack unavailable"
    except Exception as e:
        logger.error(f"eBird filtering error (allowing detection): {e}")
        return False, "Filter error - allowed by default"
```

### Database Error Recovery

```python
async def cleanup_with_retry(cleanup_service, max_retries=3):
    """Execute cleanup with automatic retry on transient failures."""
    for attempt in range(max_retries):
        try:
            stats = await cleanup_service.cleanup_detections(
                strictness="vagrant",
                region_pack="na-east-coast-2025.08"
            )
            return stats
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Cleanup attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Cleanup failed after {max_retries} attempts")
                raise
```

## Performance Considerations

### Database Attachment Overhead

- **Attach/Detach Cost**: ~10-50ms per operation depending on database size
- **Recommendation**: Reuse sessions for batch operations
- **Pattern**: Attach once, query many times, detach once

### H3 Cell Conversion

- **Cost**: ~0.1ms per conversion (negligible)
- **Caching**: Not necessary for individual requests
- **Batch Operations**: Can pre-compute H3 cells for known locations

### Query Performance

- **Single Species Lookup**: ~1-5ms with indexes
- **Location-wide Queries**: ~50-500ms depending on species count
- **Optimization**: Results should be cached for site-wide filtering (if implemented)

### Memory Usage

- **Service Overhead**: <1 MB per service instance
- **Session Overhead**: ~100 KB per attached database
- **Query Results**: <1 KB per species lookup

## Troubleshooting

### eBird Pack Not Found

**Symptom**: `FileNotFoundError: eBird pack not found: /path/to/pack.db`

**Causes**:
1. Pack file doesn't exist at expected location
2. Incorrect `region_pack` name in configuration
3. PathResolver pointing to wrong directory

**Solutions**:
```bash
# Check if pack exists
ls -la data/database/ebird_packs/

# Verify configuration
grep "region_pack" config/birdnetpi.yaml

# Install pack (if available)
# cp /path/to/pack.db data/database/ebird_packs/
```

### No Species Being Filtered

**Symptom**: All detections pass filter regardless of configuration

**Causes**:
1. eBird filtering disabled in config (`enabled: false`)
2. Detection mode set to "warn" instead of "filter"
3. Strictness too permissive for the species
4. H3 resolution mismatch between config and pack

**Solutions**:
```yaml
# Verify configuration
ebird_filtering:
  enabled: true
  detection_mode: "filter"  # Not "warn"
  detection_strictness: "vagrant"  # Or stricter
  h3_resolution: 5  # Must match pack resolution
```

### All Detections Being Filtered

**Symptom**: Every detection is blocked, even common species

**Causes**:
1. Strictness set too high (`"common"` only allows very common species)
2. H3 resolution mismatch causing location lookups to fail
3. Wrong region pack for your location
4. Pack data incomplete

**Solutions**:
```yaml
# Try more permissive settings
ebird_filtering:
  detection_strictness: "vagrant"  # Most permissive
  unknown_species_behavior: "allow"  # Allow unknowns
```

### Cleanup Removing Too Many Detections

**Symptom**: Preview shows large number of removals

**Causes**:
1. Wrong region pack for your location
2. Strictness too high for your use case
3. Many detections from migratory period not in pack data

**Solutions**:
```python
# Use limit to test incrementally
preview = await cleanup_service.preview_cleanup(
    strictness="vagrant",
    region_pack="na-east-coast-2025.08",
    limit=100  # Test with small batch first
)

# Review affected species
print(f"Affected species: {preview.species_affected}")

# Adjust strictness if needed
```

### Database Detachment Errors

**Symptom**: Log warnings about detachment failures

**Impact**: Generally harmless, resources released on session close

**Prevention**:
```python
# Always use try/finally pattern
try:
    await ebird_service.attach_to_session(session, pack_name)
    # ... queries ...
finally:
    await ebird_service.detach_from_session(session)
```

### H3 Cell Format Errors

**Symptom**: `Invalid H3 cell format` in logs

**Causes**:
1. Incorrect latitude/longitude values
2. Corrupted data in database
3. H3 library version mismatch

**Solutions**:
```python
# Validate coordinates before conversion
if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
    raise ValueError("Invalid coordinates")

# Use correct H3 format
h3_cell = h3.latlng_to_cell(latitude, longitude, resolution)
# Returns hex string like "85283473fffffff"
```

## Regional Pack Management

### Installing Regional Packs

Regional eBird packs are separate data files that must be installed:

```bash
# Create ebird_packs directory if it doesn't exist
mkdir -p data/database/ebird_packs/

# Copy pack to correct location
cp /path/to/na-east-coast-2025.08.db data/database/ebird_packs/

# Verify installation
ls -lh data/database/ebird_packs/
```

### Creating Custom Regional Packs

Regional packs can be created using the `ebird-builder` tool (separate project):

```bash
# Example: Create pack for Eastern North America
ebird-builder \
  --input /Volumes/backup/ebird/ebd_relAug-2025.txt.gz \
  --region "Eastern North America" \
  --bounds "24,-95,50,-60" \
  --h3-resolution 5 \
  --output na-east-coast-2025.08.db
```

### Pack Database Schema

Each regional pack contains a single table:

```sql
CREATE TABLE grid_species (
    h3_cell INTEGER NOT NULL,           -- H3 cell as integer
    scientific_name TEXT NOT NULL,       -- Species scientific name
    confidence_tier TEXT NOT NULL,       -- "common", "uncommon", "rare", "vagrant"
    confidence_boost REAL,               -- Optional boost multiplier (1.0-2.0)
    PRIMARY KEY (h3_cell, scientific_name)
);

CREATE INDEX idx_h3_cell ON grid_species(h3_cell);
CREATE INDEX idx_scientific_name ON grid_species(scientific_name);
```

## Integration with BirdNET-Pi Features

### Detection Manager Integration

The eBird filtering integrates with the existing `DataManager`:

```python
# Detection creation flow
detection_event → eBird Filter → DataManager.create_detection()
```

### Notification Integration

Filtered detections don't trigger notifications:

```python
if should_filter and mode == "filter":
    # No notification sent
    return {"detection_id": None, "message": "Filtered"}
else:
    # Normal notification flow
    detection = await data_manager.create_detection(event)
    await notification_manager.send_notifications(detection)
```

### Analytics Integration

Filtered detections don't appear in analytics:

```python
# Only saved detections appear in analytics
detections = data_manager.get_detections(filters)
metrics = analytics_manager.calculate_metrics(detections)
```

## Configuration Migration

### Upgrading from v1.x to v2.0

The eBird filtering feature was added in v2.0. Existing configurations will automatically get default values:

```python
# ConfigManager handles migration automatically
def migrate_v1_to_v2(config_data: dict) -> dict:
    """Add eBird filtering defaults to v1.x configs."""
    if "ebird_filtering" not in config_data:
        config_data["ebird_filtering"] = {
            "enabled": False,  # Disabled by default for safety
            "detection_mode": "filter",
            "detection_strictness": "vagrant",
            "region_pack": "",
            "h3_resolution": 5,
            "unknown_species_behavior": "allow"
        }
    return config_data
```

### Enabling eBird Filtering

After upgrading, enable the feature manually:

```yaml
# Edit config/birdnetpi.yaml
ebird_filtering:
  enabled: true  # Change from false to true
  region_pack: "na-east-coast-2025.08"  # Set your region pack
  # Other settings use sensible defaults
```

## Testing

### Unit Tests

Tests are located in:
- `/tests/birdnetpi/database/test_ebird.py` - EBirdRegionService tests
- `/tests/birdnetpi/detections/test_cleanup.py` - DetectionCleanupService tests

Run unit tests:
```bash
uv run pytest tests/birdnetpi/database/test_ebird.py -v
uv run pytest tests/birdnetpi/detections/test_cleanup.py -v
```

### Integration Tests

Tests are located in:
- `/tests/integration/test_ebird_detection_filtering_simple.py` - Detection filtering integration tests

Run integration tests:
```bash
uv run pytest tests/integration/test_ebird_detection_filtering_simple.py -v
```

### Test Coverage

Current test coverage:
- **EBirdRegionService**: 98% (31 tests)
- **DetectionCleanupService**: 94% (19 tests)
- **Integration Tests**: 5 tests, 80% pass rate

## API Versioning

The eBird filtering API endpoints follow REST principles:

- Current base path: `/api/detections/cleanup/`
- Part of the Detections API group

Future versions will maintain backwards compatibility while extending functionality to support additional cleanup operations (e.g., confidence thresholds, missing audio files).

## Security Considerations

### SQL Injection Prevention

All queries use parameterized statements:

```python
# CORRECT - parameterized query
stmt = text("""
    SELECT confidence_tier
    FROM ebird.grid_species
    WHERE h3_cell = :h3_cell
    AND scientific_name = :scientific_name
""")
result = await session.execute(stmt, {
    "h3_cell": h3_cell_int,
    "scientific_name": scientific_name
})

# WRONG - string interpolation (never do this)
stmt = f"SELECT * FROM grid_species WHERE name = '{name}'"
```

### Database Attachment Safety

Pack paths come from PathResolver, not user input:

```python
# Safe - path from trusted PathResolver
pack_path = self.path_resolver.get_ebird_pack_path(region_pack_name)
attach_sql = text(f"ATTACH DATABASE '{pack_path}' AS ebird")  # nosemgrep
```

### Admin Endpoint Protection

Detection cleanup endpoints should be protected with authentication:

```python
@router.post("/api/detections/cleanup/execute")
async def execute_cleanup(
    cleanup_request: CleanupRequest,
    current_user: User = Depends(get_admin_user)  # Require admin
):
    """Execute cleanup - admin only."""
    # ...
```

## Future Enhancements

### Planned Features

1. **Site-wide filtering** - Pre-compute allowed species list for 24-hour caching
2. **Temporal filtering** - Use eBird data to filter by season/month
3. **Confidence boosting** - Increase BirdNET confidence scores for locally common species
4. **Multi-pack support** - Support multiple regional packs with automatic selection
5. **Pack auto-updates** - Automatically download and install new regional packs
6. **Web UI** - Admin interface for cleanup operations and configuration

### Not Planned

- **Real-time eBird API** - Too slow and requires API key management
- **Global pack** - Too large (>10 GB), defeats purpose of regional filtering
- **Historical cleanup** - Use admin cleanup tool instead

## References

### eBird Data

- **eBird Basic Dataset**: https://ebird.org/data/download
- **Data Format**: https://ebird.org/data/download/ebd
- **Frequency Codes**: https://support.ebird.org/en/support/solutions/articles/48000837827

### H3 Geospatial Indexing

- **H3 Documentation**: https://h3geo.org/
- **Python Library**: https://github.com/uber/h3-py
- **Resolution Table**: https://h3geo.org/docs/core-library/restable/

### Related Documentation

- **Configuration System**: `/docs/config/README.md` (if exists)
- **Database Architecture**: `/docs/database/README.md` (if exists)
- **API Guidelines**: `/docs/api/README.md` (if exists)
