"""Tests for the AssetManifest utility."""

from pathlib import Path

import pytest

from birdnetpi.releases.asset_manifest import Asset, AssetManifest, AssetType


class TestAssetManifest:
    """Test suite for AssetManifest."""

    def test_get_all_assets(self):
        """Should return all defined assets."""
        assets = AssetManifest.get_all_assets()

        assert len(assets) == 3
        assert all(isinstance(asset, Asset) for asset in assets)

        # Check that we have the expected assets
        asset_names = {asset.name for asset in assets}
        assert "BirdNET Models" in asset_names
        assert "IOC Reference Database" in asset_names
        assert "Wikidata Reference Database" in asset_names

    def test_get_required_assets(self):
        """Should return all assets since they are all required."""
        required = AssetManifest.get_required_assets()

        # All 3 assets are required
        assert len(required) == 3
        asset_names = {asset.name for asset in required}
        assert "BirdNET Models" in asset_names
        assert "IOC Reference Database" in asset_names
        assert "Wikidata Reference Database" in asset_names

    def test_get_optional_assets(self):
        """Should return empty list since no assets are optional."""
        optional = AssetManifest.get_optional_assets()

        # No assets are optional
        assert len(optional) == 0

    def test_get_asset_paths(self, path_resolver):
        """Should return mapping of asset names to paths."""
        # Use the global path_resolver fixture
        paths = AssetManifest.get_asset_paths(path_resolver)

        assert len(paths) == 3
        assert paths["BirdNET Models"] == path_resolver.get_models_dir()
        assert paths["IOC Reference Database"] == path_resolver.get_ioc_database_path()
        assert paths["Wikidata Reference Database"] == path_resolver.get_wikidata_database_path()

    def test_get_protected_paths(self, path_resolver):
        """Should return list of protected paths."""
        # Use the global path_resolver fixture
        protected = AssetManifest.get_protected_paths(path_resolver)

        # Should include all asset paths
        assert path_resolver.get_models_dir() in protected
        assert path_resolver.get_ioc_database_path() in protected
        assert path_resolver.get_wikidata_database_path() in protected

        # Should also protect parent directories
        assert path_resolver.get_database_dir() in protected

    def test_is_protected_path(self, path_resolver):
        """Should correctly identify protected paths."""
        # Use the global path_resolver fixture
        models_dir = path_resolver.get_models_dir()
        db_dir = path_resolver.get_database_dir()

        # Create the directories only if they're in a writable location (test environment)
        try:
            models_dir.mkdir(parents=True, exist_ok=True)
            db_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            # In test environment with restricted paths, skip directory creation
            pass

        # Protected paths
        assert AssetManifest.is_protected_path(models_dir, path_resolver)
        assert AssetManifest.is_protected_path(path_resolver.get_ioc_database_path(), path_resolver)
        assert AssetManifest.is_protected_path(
            models_dir / "some_model.tflite", path_resolver
        )  # Inside protected dir

        # Non-protected paths
        assert not AssetManifest.is_protected_path(
            path_resolver.get_recordings_dir(), path_resolver
        )
        assert not AssetManifest.is_protected_path(
            path_resolver.get_database_path(), path_resolver
        )  # Runtime database (birdnetpi.db)

    def test_get_assets_by_type(self):
        """Should filter assets by type."""
        models = AssetManifest.get_assets_by_type(AssetType.MODEL)
        databases = AssetManifest.get_assets_by_type(AssetType.DATABASE)

        assert len(models) == 1
        assert models[0].name == "BirdNET Models"

        assert len(databases) == 2
        db_names = {db.name for db in databases}
        assert "IOC Reference Database" in db_names
        assert "Wikidata Reference Database" in db_names

    def test_get_asset_by_name(self):
        """Should retrieve specific asset by name."""
        asset = AssetManifest.get_asset_by_name("BirdNET Models")
        assert asset is not None
        assert asset.name == "BirdNET Models"
        assert asset.asset_type == AssetType.MODEL
        assert asset.is_directory is True

        # Non-existent asset
        assert AssetManifest.get_asset_by_name("Non-existent Asset") is None

    def test_get_release_assets(self, path_resolver):
        """Should format assets for release management."""
        # Use the global path_resolver fixture
        release_assets = AssetManifest.get_release_assets(path_resolver)

        assert len(release_assets) == 3

        # Check format of returned tuples
        for source_path, target_path, description in release_assets:
            assert isinstance(source_path, Path)
            assert isinstance(target_path, Path)
            assert isinstance(description, str)

            # Target paths should start with "data/"
            assert str(target_path).startswith("data/")

        # Check specific assets
        models_asset = next((asset for asset in release_assets if "models" in str(asset[1])), None)
        assert models_asset is not None
        assert models_asset[2] == "BirdNET TensorFlow Lite models for bird identification"


class TestAsset:
    """Test suite for Asset dataclass."""

    def test_asset_creation(self):
        """Should create Asset with correct attributes."""
        asset = Asset(
            name="Test Asset",
            path_method="get_test_path",
            description="Test description",
            asset_type=AssetType.DATABASE,
            is_directory=False,
            required=True,
        )

        assert asset.name == "Test Asset"
        assert asset.path_method == "get_test_path"
        assert asset.description == "Test description"
        assert asset.asset_type == AssetType.DATABASE
        assert asset.is_directory is False
        assert asset.required is True

    def test_asset_frozen(self):
        """Should not allow modification of Asset attributes."""
        asset = Asset(
            name="Test Asset",
            path_method="get_test_path",
            description="Test description",
            asset_type=AssetType.DATABASE,
        )

        with pytest.raises(AttributeError):
            asset.name = "Modified Name"  # type: ignore[misc]
