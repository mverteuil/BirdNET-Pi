"""Tests for the RegionPackService."""

import gzip
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from birdnetpi.releases.region_pack_service import RegionPackService
from birdnetpi.releases.registry_service import BoundingBox, RegionPackInfo


class MockHTTPResponse:
    """Mock HTTP response for testing urlopen calls."""

    def __init__(self, data: bytes, content_length: int | None = None):
        """Initialize mock response."""
        self._data = data
        self._read_called = False
        self.headers = {"Content-Length": str(content_length or len(data))}

    def __enter__(self) -> "MockHTTPResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        """Return data on first call, empty bytes on subsequent calls."""
        if self._read_called:
            return b""
        self._read_called = True
        return self._data


class MockHTTPResponseError:
    """Mock HTTP response that raises an error on read."""

    def __init__(self, error: Exception):
        """Initialize mock response."""
        self._error = error
        self.headers = {"Content-Length": "1000"}

    def __enter__(self) -> "MockHTTPResponseError":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        """Raise an error."""
        raise self._error


def make_region_pack_info(
    region_id: str = "test-region-001",
    download_url: str | None = "https://example.com/pack.db.gz",
    total_size_mb: float = 10.0,
) -> RegionPackInfo:
    """Create a valid RegionPackInfo for testing."""
    return RegionPackInfo(
        region_id=region_id,
        release_name=f"{region_id}-v1",
        h3_cells=["8615f2", "8615f3"],
        pack_count=2,
        total_size_mb=total_size_mb,
        resolution=6,
        center={"lat": 45.0, "lon": -75.0},
        bbox=BoundingBox(min_lat=44.0, max_lat=46.0, min_lon=-76.0, max_lon=-74.0),
        download_url=download_url,
    )


class TestRegionPackService:
    """Test suite for RegionPackService."""

    def test_init(self, path_resolver):
        """Should initialize with path resolver and registry service."""
        service = RegionPackService(path_resolver)

        assert service.path_resolver == path_resolver
        assert service.registry_service is not None

    def test_get_install_path(self, path_resolver):
        """Should return correct install path for a region."""
        service = RegionPackService(path_resolver)
        expected_dir = path_resolver.data_dir / "database"

        result = service.get_install_path("na-east-054")

        assert result == expected_dir / "na-east-054.db"

    def test_get_install_path_creates_directory(self, path_resolver):
        """Should create database directory if it doesn't exist."""
        service = RegionPackService(path_resolver)
        db_dir = path_resolver.data_dir / "database"

        # Ensure directory doesn't exist first
        if db_dir.exists():
            import shutil

            shutil.rmtree(db_dir)

        service.get_install_path("na-east-054")

        assert db_dir.exists()

    def test_is_installed_returns_false_when_not_installed(self, path_resolver):
        """Should return False when pack is not installed."""
        service = RegionPackService(path_resolver)

        result = service.is_installed("nonexistent-region-123")

        assert result is False

    def test_is_installed_returns_true_when_installed(self, path_resolver):
        """Should return True when pack is installed."""
        service = RegionPackService(path_resolver)

        # Create the database file
        install_path = service.get_install_path("test-region-001")
        install_path.parent.mkdir(parents=True, exist_ok=True)
        install_path.touch()

        result = service.is_installed("test-region-001")

        assert result is True

    def test_find_pack_for_coordinates_delegates_to_registry(self, path_resolver):
        """Should delegate coordinate lookup to registry service."""
        service = RegionPackService(path_resolver)
        mock_pack = MagicMock(spec=RegionPackInfo)

        with patch.object(
            service.registry_service,
            "find_pack_for_coordinates",
            return_value=mock_pack,
        ) as mock_find:
            result = service.find_pack_for_coordinates(45.0, -75.0)

            mock_find.assert_called_once_with(45.0, -75.0)
            assert result == mock_pack

    def test_download_and_install_raises_without_url(self, path_resolver):
        """Should raise ValueError when pack has no download URL."""
        service = RegionPackService(path_resolver)
        pack = make_region_pack_info(region_id="test-001", download_url=None)

        with pytest.raises(ValueError, match="no download URL"):
            service.download_and_install(pack)

    def test_download_and_install_raises_if_exists_without_force(self, path_resolver):
        """Should raise FileExistsError when pack exists and force is False."""
        service = RegionPackService(path_resolver)

        pack = make_region_pack_info(region_id="existing-pack-001", total_size_mb=10.0)

        # Create existing file using the release_name (which is used for install path)
        install_path = service.get_install_path(pack.release_name)
        install_path.parent.mkdir(parents=True, exist_ok=True)
        install_path.touch()

        with pytest.raises(FileExistsError, match="already installed"):
            service.download_and_install(pack)

    def test_download_from_url_success(self, path_resolver, tmp_path):
        """Should download and extract gzipped database file."""
        service = RegionPackService(path_resolver)

        # Create a test gzipped database
        test_content = b"SQLite format 3\x00" + b"\x00" * 100
        compressed = gzip.compress(test_content)

        # Use MockHTTPResponse instead of MagicMock
        mock_response = MockHTTPResponse(compressed)

        with patch(
            "birdnetpi.releases.region_pack_service.urlopen",
            return_value=mock_response,
        ):
            result = service.download_from_url(
                release_name="download-test-001",
                download_url="https://example.com/pack.db.gz",
                size_mb=1.0,
            )

        assert result.exists()
        assert result.name == "download-test-001.db"
        # Check content was extracted
        assert result.read_bytes() == test_content

    def test_download_from_url_with_progress_callback(self, path_resolver):
        """Should call progress callback during download."""
        service = RegionPackService(path_resolver)

        # Create test data
        test_content = b"test database content"
        compressed = gzip.compress(test_content)

        # Track progress calls
        progress_calls: list[tuple[float, float]] = []

        def track_progress(downloaded: float, total: float) -> None:
            progress_calls.append((downloaded, total))

        # Use MockHTTPResponse instead of MagicMock
        mock_response = MockHTTPResponse(compressed)

        with patch(
            "birdnetpi.releases.region_pack_service.urlopen",
            return_value=mock_response,
        ):
            service.download_from_url(
                release_name="progress-test-001",
                download_url="https://example.com/pack.db.gz",
                progress_callback=track_progress,
            )

        # Should have been called at least once
        assert len(progress_calls) > 0

    def test_download_from_url_cleans_up_on_failure(self, path_resolver):
        """Should clean up partial files on download failure."""
        service = RegionPackService(path_resolver)

        # Use MockHTTPResponseError to raise an error on read
        mock_response = MockHTTPResponseError(Exception("Network error"))

        with (
            patch(
                "birdnetpi.releases.region_pack_service.urlopen",
                return_value=mock_response,
            ),
            pytest.raises(Exception, match="Network error"),
        ):
            service.download_from_url(
                release_name="cleanup-test-001",
                download_url="https://example.com/pack.db.gz",
            )

        # Verify no partial files remain
        install_path = service.get_install_path("cleanup-test-001")
        assert not install_path.exists()
        assert not install_path.with_suffix(".db.gz").exists()

    def test_download_and_install_delegates_to_download_from_url(self, path_resolver):
        """Should delegate to download_from_url with pack info."""
        service = RegionPackService(path_resolver)
        pack = make_region_pack_info(region_id="delegate-test-001", total_size_mb=15.5)

        with patch.object(
            service,
            "download_from_url",
            return_value=Path("/fake/path.db"),
        ) as mock_download:
            result = service.download_and_install(pack, force=True)

            mock_download.assert_called_once_with(
                release_name="delegate-test-001-v1",
                download_url="https://example.com/pack.db.gz",
                size_mb=15.5,
                force=True,
                progress_callback=None,
            )
            assert result == Path("/fake/path.db")

    def test_download_from_url_force_overwrites_existing(self, path_resolver):
        """Should overwrite existing file when force is True."""
        service = RegionPackService(path_resolver)

        # Create existing file
        install_path = service.get_install_path("force-test-001")
        install_path.parent.mkdir(parents=True, exist_ok=True)
        install_path.write_text("old content")

        # Create test data
        new_content = b"new database content"
        compressed = gzip.compress(new_content)

        # Use MockHTTPResponse instead of MagicMock
        mock_response = MockHTTPResponse(compressed)

        with patch(
            "birdnetpi.releases.region_pack_service.urlopen",
            return_value=mock_response,
        ):
            result = service.download_from_url(
                release_name="force-test-001",
                download_url="https://example.com/pack.db.gz",
                force=True,
            )

        assert result.exists()
        assert result.read_bytes() == new_content
