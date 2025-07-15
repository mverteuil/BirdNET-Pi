from unittest.mock import patch

import pytest

from birdnetpi.utils.species_list_utils import SpeciesListUtils


@pytest.fixture
def species_list_utils():
    """Provide a SpeciesListUtils instance for testing."""
    return SpeciesListUtils(species_list_path="/path/to/species_list.txt")


@patch("birdnetpi.utils.species_list_utils.os.path.exists", return_value=True)
@patch("birdnetpi.utils.species_list_utils.open")
def test_load_species_list_success(mock_open, mock_exists, species_list_utils):
    """Should return a list of species."""
    mock_open.return_value.__enter__.return_value.__iter__.return_value = [
        "species1\n",
        "species2\n",
        "species3\n",
    ]
    species_list = species_list_utils.load_species_list()
    assert species_list == ["species1", "species2", "species3"]


@patch("birdnetpi.utils.species_list_utils.os.path.exists", return_value=False)
def test_load_species_list_file_not_found(mock_exists, species_list_utils):
    """Should raise FileNotFoundError if the file is not found."""
    with pytest.raises(FileNotFoundError):
        species_list_utils.load_species_list()
