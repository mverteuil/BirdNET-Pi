"""Detection-related API contract models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ==================== Request Models ====================


class DetectionEvent(BaseModel):
    """Represents a detection event with associated metadata."""

    # Detection ID (UUID for distributed system compatibility)
    id: UUID | None = None

    # Species identification (parsed from tensor output)
    species_tensor: str  # Raw tensor output: "Scientific name_Common Name"
    scientific_name: str  # Parsed: "Genus species" (IOC primary key)
    common_name: str  # Standardized common name from tensor

    # Detection metadata
    confidence: float
    timestamp: datetime

    # Audio data
    audio_data: str  # Base64-encoded audio bytes
    sample_rate: int
    channels: int

    # Optional fields
    spectrogram_path: str | None = None
    latitude: float
    longitude: float
    species_confidence_threshold: float
    week: int
    sensitivity_setting: float
    overlap: float


class LocationUpdate(BaseModel):
    """Request model for updating location settings."""

    latitude: float
    longitude: float


# ==================== Common Response Components ====================


class PaginationInfo(BaseModel):
    """Pagination metadata for list responses."""

    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    has_prev: bool = Field(..., description="Whether there is a previous page")
    has_next: bool = Field(..., description="Whether there is a next page")


class DetectionResponse(BaseModel):
    """A single detection in API responses."""

    id: UUID
    scientific_name: str
    common_name: str
    confidence: float
    timestamp: datetime
    date: str | None = None
    time: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    family: str | None = None
    genus: str | None = None
    order_name: str | None = None
    audio_file_id: UUID | None = None
    # First detection metadata (optional, populated when requested)
    is_first_ever: bool | None = None
    is_first_in_period: bool | None = None
    first_ever_detection: datetime | None = None
    first_period_detection: datetime | None = None


class SpeciesInfo(BaseModel):
    """Species information with detection counts."""

    name: str = Field(..., description="Display name (common or scientific)")
    scientific_name: str = Field(..., description="Scientific name")
    detection_count: int = Field(..., description="Number of detections")
    is_first_ever: bool = Field(default=False, description="Whether this is first detection ever")
    first_ever_detection: datetime | None = Field(None, description="Timestamp of first detection")
    family: str | None = None
    genus: str | None = None
    order: str | None = None


class TaxonomySpeciesItem(BaseModel):
    """Species in taxonomy responses."""

    scientific_name: str
    common_name: str
    count: int


# ==================== Response Models ====================


class DetectionCreatedResponse(BaseModel):
    """Response after creating a detection."""

    message: str = Field(..., description="Success message")
    detection_id: UUID | None = Field(..., description="ID of created detection (None if filtered)")


class RecentDetectionsResponse(BaseModel):
    """Response for recent detections endpoint."""

    detections: list[DetectionResponse] = Field(..., description="List of recent detections")
    count: int = Field(..., description="Number of detections returned")


class DetectionsSummary(BaseModel):
    """Summary statistics for detections."""

    total_detections: int = Field(..., description="Total number of detections")
    unique_species: int = Field(..., description="Number of unique species")
    date_range: str | None = Field(None, description="Date range of detections")
    avg_confidence: float | None = Field(None, description="Average confidence score")


class PaginatedDetectionsResponse(BaseModel):
    """Response for paginated detections endpoint."""

    detections: list[DetectionResponse] = Field(..., description="List of detection data")
    pagination: PaginationInfo = Field(..., description="Pagination metadata")
    summary: DetectionsSummary = Field(..., description="Summary statistics")


class DetectionCountResponse(BaseModel):
    """Response for detection count endpoint."""

    date: str = Field(..., description="Date in ISO format")
    count: int = Field(..., description="Number of detections on this date")


class BestRecordingsFilters(BaseModel):
    """Filters applied to best recordings query."""

    family: str | None = None
    genus: str | None = None
    species: str | None = None
    min_confidence: float = Field(..., description="Minimum confidence threshold")


class BestRecordingsResponse(BaseModel):
    """Response for best recordings endpoint."""

    recordings: list[DetectionResponse] = Field(..., description="Best recordings")
    count: int = Field(..., description="Number of recordings returned")
    pagination: PaginationInfo = Field(..., description="Pagination metadata")
    avg_confidence: float = Field(..., description="Average confidence across recordings")
    date_range: str = Field(..., description="Date range of recordings")
    unique_species: int = Field(..., description="Number of unique species")
    filters: BestRecordingsFilters = Field(..., description="Applied filters")


class TaxonomyFamiliesResponse(BaseModel):
    """Response for taxonomy families endpoint."""

    families: list[str] = Field(..., description="List of family names")
    count: int = Field(..., description="Number of families")


class TaxonomyGeneraResponse(BaseModel):
    """Response for taxonomy genera endpoint."""

    genera: list[str] = Field(..., description="List of genus names")
    family: str = Field(..., description="Parent family")
    count: int = Field(..., description="Number of genera")


class TaxonomySpeciesResponse(BaseModel):
    """Response for taxonomy species endpoint."""

    species: list[TaxonomySpeciesItem] = Field(..., description="List of species")
    genus: str = Field(..., description="Parent genus")
    family: str | None = Field(None, description="Parent family filter")
    count: int = Field(..., description="Number of species")


class SpeciesFrequency(BaseModel):
    """Species frequency information."""

    species: str = Field(..., description="Species name")
    count: int = Field(..., description="Detection count")
    percentage: float = Field(..., description="Percentage of total detections")


class DetectionsSummaryResponse(BaseModel):
    """Response for detections summary endpoint."""

    species_frequency: list[SpeciesFrequency] = Field(..., description="Species frequency data")
    subtitle: str = Field(..., description="Formatted subtitle")
    statistics: str = Field(..., description="Formatted statistics HTML")
    species_count: int = Field(..., description="Number of unique species")
    total_detections: int = Field(..., description="Total number of detections")


class LocationUpdateResponse(BaseModel):
    """Response after updating detection location."""

    message: str = Field(..., description="Success message")
    detection_id: str = Field(..., description="ID of updated detection")
    latitude: float = Field(..., description="New latitude")
    longitude: float = Field(..., description="New longitude")


class DetectionDetailResponse(BaseModel):
    """Response for single detection detail endpoint."""

    id: UUID
    scientific_name: str
    common_name: str
    confidence: float
    timestamp: datetime
    latitude: float | None = None
    longitude: float | None = None
    species_confidence_threshold: float | None = None
    week: int | None = None
    sensitivity_setting: float | None = None
    overlap: float | None = None
    ioc_english_name: str | None = None
    translated_name: str | None = None
    family: str | None = None
    genus: str | None = None
    order_name: str | None = None


class SpeciesSummaryResponse(BaseModel):
    """Response for species summary endpoint."""

    species: list[SpeciesInfo] = Field(..., description="List of species with counts")
    count: int = Field(..., description="Number of species")
    total_detections: int = Field(..., description="Total detections across all species")
    period: str | None = Field(None, description="Time period filter")
    period_label: str | None = Field(None, description="Human-readable period label")


class SpeciesChecklistItem(BaseModel):
    """A single species in the checklist with detection status.

    Represents a species from the IOC reference database with its detection metadata.
    This is NOT a detection record, but a species record with detection status.
    """

    # Species identification
    scientific_name: str = Field(..., description="Scientific name (IOC primary key)")
    common_name: str = Field(..., description="IOC English name")
    translated_name: str | None = Field(None, description="Localized common name")

    # Taxonomy
    family: str | None = Field(None, description="Taxonomic family")
    genus: str | None = Field(None, description="Taxonomic genus")
    order_name: str | None = Field(None, description="Taxonomic order")

    # Detection status
    is_detected: bool = Field(..., description="Whether this species has been detected")
    detection_count: int = Field(default=0, description="Number of detections")
    latest_detection: datetime | None = Field(
        None, description="Timestamp of most recent detection"
    )

    # Reference database fields (may be NULL if not in schema yet)
    image_url: str | None = Field(None, description="Wikidata image URL")
    conservation_status: str | None = Field(
        None, description="IUCN conservation status from Wikidata"
    )
    bow_url: str | None = Field(None, description="Birds of the World URL from IOC")


class SpeciesChecklistResponse(BaseModel):
    """Response for species checklist endpoint."""

    species: list[SpeciesChecklistItem] = Field(
        ..., description="List of species with detection status"
    )
    pagination: PaginationInfo = Field(..., description="Pagination metadata")
    filters: dict[str, str | None] = Field(..., description="Applied filters")
    total_species: int = Field(..., description="Total number of species in checklist")
    detected_species: int = Field(..., description="Number of detected species")
    undetected_species: int = Field(..., description="Number of undetected species")
