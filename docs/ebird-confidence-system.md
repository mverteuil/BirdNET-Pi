# eBird Regional Confidence System

## Overview

The eBird Regional Confidence System integrates eBird observation data to provide location-aware confidence scoring for bird detections. It uses H3 geospatial indexing to match detections with regional bird occurrence patterns, applying intelligent adjustments for spatial uncertainty, data quality, and temporal variations.

## Key Features

### 1. H3 Geospatial Indexing

The system uses Uber's H3 hierarchical hexagonal grid system for efficient spatial lookups:

- **Resolution 5**: ~252 km² hexagons for regional coverage
- **Hex-to-hex distance**: Calculated using H3's grid_distance function
- **Neighbor search**: Searches surrounding k-rings for species data

### 2. Schema Architecture

**Region Pack Database Tables:**

```sql
-- Species lookup table (maps scientific names to Avibase IDs)
CREATE TABLE species_lookup (
    avibase_id TEXT PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    -- ... other fields
);

-- Grid species data (H3 cell × species observations)
CREATE TABLE grid_species (
    h3_cell INTEGER,              -- H3 cell as integer
    avibase_id TEXT,              -- FK to species_lookup
    confidence_tier TEXT,         -- common/uncommon/rare/vagrant
    confidence_boost REAL,        -- Base boost value (1.0-2.0)
    yearly_frequency REAL,        -- Annual observation frequency
    total_observations INTEGER,   -- Total observation count
    total_checklists INTEGER,     -- Total checklists with species
    monthly_frequency_json TEXT,  -- JSON array of 12 monthly frequencies
    PRIMARY KEY (h3_cell, avibase_id)
);
```

**Detection Tracking Fields:**

All eBird parameters are stored with each detection for reproducibility:

```python
class Detection(SQLModel, table=True):
    # Model versioning
    tensor_model: str | None = None          # BirdNET model used
    metadata_model: str | None = None        # Metadata filter model

    # eBird confidence parameters
    ebird_confidence_tier: str | None = None  # Tier at matched cell
    ebird_confidence_boost: float | None = None  # Final calculated boost
    ebird_h3_cell: str | None = None         # Matched H3 cell (hex)
    ebird_ring_distance: int | None = None   # Distance from user (rings)
    ebird_region_pack: str | None = None     # Pack name + version
```

### 3. Neighbor Search Algorithm

When a species isn't found in the exact user location cell, the system searches surrounding hexagons:

```python
# User location → H3 cell
user_cell = h3.latlng_to_cell(latitude, longitude, resolution=5)

# Generate neighbor cells (k=0 to max_rings)
neighbor_cells = {user_cell}  # Start with exact match
for k in range(1, max_rings + 1):
    neighbor_cells.update(h3.grid_ring(user_cell, k))

# Query all neighbors in single database call
# Find closest match by minimum ring distance
```

**Visual representation:**

```
Ring 0 (exact):     1 cell    (user location)
Ring 1 (adjacent):  6 cells   (immediate neighbors)
Ring 2 (2nd ring): 12 cells   (next layer out)
Total for k=2:     19 cells searched
```

### 4. Confidence Calculation Formula

The final confidence boost is calculated by combining multiple factors:

```
final_boost = base_boost ×
              ring_multiplier ×
              quality_multiplier ×
              temporal_multiplier
```

**Components:**

1. **Base Boost** (from pack data): Pre-calculated boost value (1.0-2.0) based on regional occurrence patterns

2. **Ring Multiplier** (distance decay):
   ```
   ring_multiplier = 1.0 - (ring_distance × decay_per_ring)

   Example with decay_per_ring = 0.15:
   - Ring 0 (exact match): 1.00 × base
   - Ring 1 (adjacent):    0.85 × base
   - Ring 2 (2nd ring):    0.70 × base
   ```

3. **Quality Multiplier** (observation quality):
   ```
   quality_multiplier = base + (range × quality_score)

   Example with base=0.7, range=0.3:
   - Poor quality (0.0):    0.70
   - Medium quality (0.5):  0.85
   - High quality (1.0):    1.00
   ```

4. **Temporal Multiplier** (seasonal patterns):
   ```
   Based on monthly_frequency for current month:
   - Absent (freq = 0.0):       0.80 (absence penalty)
   - Off-season (freq < 0.1):   1.00 (no penalty)
   - Normal (0.1 ≤ freq ≤ 0.5): 1.00 (baseline)
   - Peak season (freq > 0.5):  1.00 (optional boost)
   ```

**Complete Example:**

```python
# Input
base_boost = 1.5              # From pack data
ring_distance = 1             # Found in adjacent cell
month_frequency = 0.3         # 30% observation rate in June

# Configuration
decay_per_ring = 0.15
quality_base = 0.7
quality_range = 0.3
quality_score = 0.8           # Good quality data

# Calculation
ring_mult = 1.0 - (1 × 0.15) = 0.85
quality_mult = 0.7 + (0.3 × 0.8) = 0.94
temporal_mult = 1.0           # Normal season

final_boost = 1.5 × 0.85 × 0.94 × 1.0 = 1.20
```

### 5. Configuration Parameters

All parameters are user-adjustable via `EBirdFilterConfig`:

```python
class EBirdFilterConfig(BaseModel):
    # Core settings
    enabled: bool = False
    h3_resolution: int = 5
    detection_mode: str = "off"  # off/warn/filter
    detection_strictness: str = "vagrant"

    # Neighbor search
    neighbor_search_enabled: bool = True
    neighbor_search_max_rings: int = 2
    neighbor_boost_decay_per_ring: float = 0.15

    # Quality adjustments
    quality_multiplier_base: float = 0.7
    quality_multiplier_range: float = 0.3

    # Temporal adjustments
    use_monthly_frequency: bool = True
    absence_penalty_factor: float = 0.8
    peak_season_boost: float = 1.0
    off_season_penalty: float = 1.0
```

## Service Methods

### Core Query Methods

#### `attach_to_session(session, region_pack_name)`

Attaches an eBird region pack database to the session for querying.

```python
await ebird_service.attach_to_session(session, "africa-east-2025.08")
```

**Database Operation:**
```sql
ATTACH DATABASE '/path/to/africa-east-2025.08.db' AS ebird
```

#### `get_species_confidence_tier(session, scientific_name, h3_cell)`

Returns the confidence tier for a species in a specific H3 cell.

**Query:**
```sql
SELECT gs.confidence_tier
FROM ebird.grid_species gs
JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
WHERE gs.h3_cell = :h3_cell
  AND sl.scientific_name = :scientific_name
```

**Returns:** `"common"` | `"uncommon"` | `"rare"` | `"vagrant"` | `None`

#### `get_confidence_boost(session, scientific_name, h3_cell)`

Returns the base confidence boost for a species in a specific H3 cell.

**Returns:** `float` (1.0-2.0) | `None`

#### `is_species_in_region(session, scientific_name, h3_cell)`

Checks if a species has any eBird data for a specific H3 cell.

**Returns:** `bool`

### Advanced Query Methods

#### `get_confidence_with_neighbors(session, scientific_name, latitude, longitude, config, month=None)`

**Primary method for detection processing.** Searches user location and surrounding neighbors, applying all confidence adjustments.

**Algorithm:**

1. Convert lat/lon → H3 cell
2. Generate neighbor cells (rings 0 to max_k)
3. Query all cells in single database call
4. Find closest match by minimum grid distance
5. Calculate distance-based multiplier
6. Apply quality multiplier
7. Apply temporal multiplier (if month provided)
8. Return complete confidence data

**Returns:**
```python
{
    "confidence_boost": 1.20,        # Final calculated boost
    "confidence_tier": "common",     # Tier at matched cell
    "h3_cell": "85283473fffffff",    # Matched cell (hex string)
    "ring_distance": 1,              # Rings from user location
    "region_pack": None,             # Filled by caller
}
```

**Returns `None`** if species not found within searched rings.

#### `get_allowed_species_for_location(session, h3_cell, strictness)`

Returns set of species allowed for site-wide filtering based on strictness level.

**Strictness Levels:**

- `"vagrant"`: Allows common, uncommon, rare (excludes vagrant)
- `"rare"`: Allows common, uncommon
- `"uncommon"`: Allows common only
- `"common"`: Allows common only

**Query Example (strictness="rare"):**
```sql
SELECT DISTINCT sl.scientific_name
FROM ebird.grid_species gs
JOIN ebird.species_lookup sl ON gs.avibase_id = sl.avibase_id
WHERE gs.h3_cell = :h3_cell
  AND gs.confidence_tier IN ('uncommon', 'common')
```

**Returns:** `set[str]` of scientific names

**Caching:** Results should be cached for 24 hours as regional species lists don't change frequently.

## Integration Points

### Detection Processing

The system integrates into the detection pipeline at the point where detections are created:

```python
# Pseudocode for integration
async def process_detection(
    scientific_name: str,
    confidence: float,
    latitude: float,
    longitude: float,
):
    # Get eBird confidence data with neighbor search
    ebird_data = await ebird_service.get_confidence_with_neighbors(
        session=session,
        scientific_name=scientific_name,
        latitude=latitude,
        longitude=longitude,
        config=config,
        month=current_month,
    )

    # Create detection with eBird parameters
    detection = Detection(
        scientific_name=scientific_name,
        confidence=confidence,
        tensor_model="BirdNET_GLOBAL_6K_V2.4_Model_FP16",
        metadata_model="BirdNET_GLOBAL_6K_V2.4_MData_Model_FP16",
        ebird_confidence_tier=ebird_data["confidence_tier"] if ebird_data else None,
        ebird_confidence_boost=ebird_data["confidence_boost"] if ebird_data else None,
        ebird_h3_cell=ebird_data["h3_cell"] if ebird_data else None,
        ebird_ring_distance=ebird_data["ring_distance"] if ebird_data else None,
        ebird_region_pack="africa-east-2025.08" if ebird_data else None,
    )

    # Apply boost to confidence if in detection mode
    if config.ebird_filtering.detection_mode == "filter" and ebird_data:
        adjusted_confidence = confidence * ebird_data["confidence_boost"]
        # Use adjusted_confidence for threshold comparison
```

### Site-Wide Filtering

For site-wide species filtering (e.g., species checklist):

```python
async def get_site_species_list(latitude: float, longitude: float):
    # Get user's H3 cell
    h3_cell = h3.latlng_to_cell(latitude, longitude, config.h3_resolution)

    # Get allowed species based on strictness
    allowed_species = await ebird_service.get_allowed_species_for_location(
        session=session,
        h3_cell=h3_cell,
        strictness=config.detection_strictness,
    )

    # Cache result for 24 hours
    cache.set(f"allowed_species:{h3_cell}:{strictness}", allowed_species, ttl=86400)

    return allowed_species
```

## Database Performance

### Query Optimization

1. **Primary Key**: `(h3_cell, avibase_id)` enables fast lookups
2. **Integer H3 cells**: Faster comparisons than hex strings
3. **Single JOIN**: Minimal overhead for species lookup
4. **Batch neighbor query**: One query for all rings vs. separate queries per ring

### Expected Performance

- **Single cell lookup**: <1ms
- **Neighbor search (k=2, 19 cells)**: <5ms
- **Site species list (common strictness)**: <10ms

### Indexing

```sql
-- Automatic from PRIMARY KEY
CREATE INDEX idx_grid_species_pk ON grid_species(h3_cell, avibase_id);

-- Additional indexes for performance
CREATE INDEX idx_species_lookup_name ON species_lookup(scientific_name);
CREATE INDEX idx_grid_species_tier ON grid_species(confidence_tier);
```

## Testing

### Unit Tests

Test each method independently:

```python
async def test_get_species_confidence_tier(session, ebird_service):
    """Should return confidence tier for species in cell."""
    tier = await ebird_service.get_species_confidence_tier(
        session, "Passer domesticus", "85283473fffffff"
    )
    assert tier in ["common", "uncommon", "rare", "vagrant"]
```

### Integration Tests

Test the complete workflow:

```python
async def test_neighbor_search_with_decay(session, ebird_service, config):
    """Should find species in adjacent cell with distance decay."""
    data = await ebird_service.get_confidence_with_neighbors(
        session=session,
        scientific_name="Passer domesticus",
        latitude=-1.286389,
        longitude=36.817223,
        config=config,
        month=6,
    )

    assert data is not None
    assert data["ring_distance"] >= 0
    assert 1.0 <= data["confidence_boost"] <= 2.0
    assert data["confidence_tier"] in ["common", "uncommon", "rare", "vagrant"]
```

### Test Data Requirements

- Sample eBird region pack with known species distributions
- Test coordinates with known H3 cells
- Known species at various confidence tiers
- Monthly frequency data for temporal testing

## Error Handling

### Common Error Cases

1. **Pack not found**: Raise `FileNotFoundError` with pack path
2. **Invalid H3 cell**: Log error and return `None`
3. **Species not found**: Return `None` (not an error - species may be vagrant/absent)
4. **Database connection**: Let SQLAlchemy exceptions propagate

### Logging

```python
logger.debug(
    "Found %s in cell %s (distance: %d rings, boost: %.2f → %.2f)",
    scientific_name,
    matched_cell_hex,
    min_distance,
    base_boost,
    final_boost,
)
```

## Future Enhancements

### Potential Improvements

1. **Quality Metrics Extraction**: If region pack schema adds separate quality fields, extract and use instead of pre-calculated base_boost

2. **Seasonal Adjustments**: Add breeding/migration season awareness for more sophisticated temporal multipliers

3. **Confidence Bands**: Instead of point boost values, provide confidence intervals (e.g., 1.2 ± 0.3)

4. **Multi-Pack Support**: Query multiple overlapping region packs and merge results

5. **Cache Optimization**: Add in-memory cache for frequently queried species/cell combinations

### Configuration Evolution

The current simple parameter approach can evolve to structured components without breaking changes:

```python
# Future: Structured components (maintains backward compatibility)
class EBirdFilterConfig(BaseModel):
    # Simple parameters (current)
    neighbor_search_max_rings: int = 2
    neighbor_boost_decay_per_ring: float = 0.15

    # OR: Structured components (future enhancement)
    neighbor_search: NeighborSearchConfig | None = None
```

## References

- **H3 Geospatial Index**: https://h3geo.org/
- **eBird Basic Dataset**: https://ebird.org/data/download
- **SQLAlchemy Async**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- **Pydantic Configuration**: https://docs.pydantic.dev/latest/

## Version History

- **v1.0.0** (2025-10-18): Initial implementation with neighbor search, quality multipliers, and temporal adjustments
