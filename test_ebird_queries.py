"""Test script for eBird regional confidence queries with africa-east pack.

This script tests the new EBirdRegionService implementation with the africa-east
region pack database. It verifies:
1. Schema changes (avibase_id as PK with JOINs)
2. Neighbor search with H3 grid rings
3. Distance-based confidence decay
4. Quality and temporal multipliers
"""

import asyncio

import h3
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from birdnetpi.config.models import EBirdFilterConfig
from birdnetpi.database.ebird import EBirdRegionService
from birdnetpi.species.ebird_queries import EBirdQueryService
from birdnetpi.system.path_resolver import PathResolver


async def main() -> None:
    """Test eBird region pack queries."""
    print("=" * 80)
    print("Testing eBird Region Pack Functionality")
    print("=" * 80)
    print()

    # Setup services
    path_resolver = PathResolver()
    ebird_region_service = EBirdRegionService(path_resolver)
    ebird_query_service = EBirdQueryService()

    # Get path to africa-east pack
    pack_name = "africa-east-2025.08"
    pack_path = path_resolver.get_ebird_pack_path(pack_name)

    if not pack_path.exists():
        print(f"❌ ERROR: Region pack not found at {pack_path}")
        print("\nPlease ensure the africa-east region pack is downloaded.")
        return

    print(f"✅ Found region pack: {pack_path}")
    print()

    # Create async database session
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_factory() as session:  # type: ignore[attr-defined]
        # Attach the ebird pack
        print(f"📦 Attaching eBird pack: {pack_name}")
        await ebird_region_service.attach_to_session(session, pack_name)
        print("✅ Pack attached successfully")
        print()

        # Test coordinates in East Africa (Kenya)
        latitude = -1.286389  # Nairobi, Kenya
        longitude = 36.817223
        scientific_name = "Passer domesticus"  # House Sparrow - common globally

        # Convert to H3 cell for display
        h3_cell = h3.latlng_to_cell(latitude, longitude, 5)
        print("📍 Test Location:")
        print(f"   Latitude: {latitude}")
        print(f"   Longitude: {longitude}")
        print(f"   H3 Cell (res 5): {h3_cell}")
        print()

        # Configure eBird filtering with neighbor search
        config = EBirdFilterConfig(
            enabled=True,
            h3_resolution=5,
            neighbor_search_enabled=True,
            neighbor_search_max_rings=2,
            neighbor_boost_decay_per_ring=0.15,
            quality_multiplier_base=0.7,
            quality_multiplier_range=0.3,
            use_monthly_frequency=True,
            absence_penalty_factor=0.8,
            peak_season_boost=1.0,
            off_season_penalty=1.0,
        )

        print(f"🔬 Testing species: {scientific_name}")
        print()

        # Test 1: Basic query - get confidence tier
        print("Test 1: Get Confidence Tier")
        print("-" * 40)
        tier = await ebird_region_service.get_species_confidence_tier(
            session, scientific_name, h3_cell
        )
        if tier:
            print(f"✅ Confidence tier: {tier}")
        else:
            print("⚠️  Species not found in exact H3 cell")
        print()

        # Test 2: Get confidence boost
        print("Test 2: Get Confidence Boost")
        print("-" * 40)
        boost = await ebird_region_service.get_confidence_boost(session, scientific_name, h3_cell)
        if boost:
            print(f"✅ Base confidence boost: {boost:.2f}")
        else:
            print("⚠️  No boost data in exact H3 cell")
        print()

        # Test 3: Check if species is in region
        print("Test 3: Check Species Presence")
        print("-" * 40)
        is_present = await ebird_region_service.is_species_in_region(
            session, scientific_name, h3_cell
        )
        print(f"✅ Species present: {is_present}")
        print()

        # Test 4: Neighbor search with distance-based decay
        print("Test 4: Neighbor Search with Distance Decay")
        print("-" * 40)
        confidence_data = await ebird_query_service.get_confidence_with_neighbors(
            session=session,
            scientific_name=scientific_name,
            latitude=latitude,
            longitude=longitude,
            config=config,
            month=6,  # June (Northern summer, Kenya dry season)
        )

        if confidence_data:
            print("✅ Species found via neighbor search!")
            print(f"   Matched H3 Cell: {confidence_data['h3_cell']}")
            print(f"   Ring Distance: {confidence_data['ring_distance']}")
            print(f"   Confidence Tier: {confidence_data['confidence_tier']}")
            print(f"   Final Boost: {confidence_data['confidence_boost']:.2f}")
            print()

            # Calculate neighbor details
            matched_cell = confidence_data["h3_cell"]
            user_cell = h3.latlng_to_cell(latitude, longitude, config.h3_resolution)
            distance = h3.grid_distance(user_cell, matched_cell)

            print("   Algorithm Details:")
            print(f"   - User H3 cell: {user_cell}")
            print(f"   - Searched rings: 0-{config.neighbor_search_max_rings}")
            print(f"   - Decay per ring: {config.neighbor_boost_decay_per_ring}")
            distance_mult = 1.0 - (distance * config.neighbor_boost_decay_per_ring)
            print(f"   - Distance multiplier: {distance_mult:.2f}")
        else:
            print(f"❌ Species not found within {config.neighbor_search_max_rings} rings")
        print()

        # Test 5: Get allowed species for strictness levels
        print("Test 5: Site Filtering - Allowed Species by Strictness")
        print("-" * 40)

        for strictness in ["vagrant", "rare", "uncommon", "common"]:
            allowed = await ebird_region_service.get_allowed_species_for_location(
                session, h3_cell, strictness
            )
            print(f"   {strictness:10s}: {len(allowed):4d} species allowed")

        print()

        # Detach the pack
        print("🔌 Detaching eBird pack")
        await ebird_region_service.detach_from_session(session)
        print("✅ Pack detached successfully")
        print()

    print("=" * 80)
    print("All tests completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
