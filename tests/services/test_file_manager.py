import pytest

from birdnetpi.services.file_manager import FileManager


@pytest.fixture
def file_manager(tmp_path):
    """Provide a FileManager instance for testing."""
    return FileManager(base_path=str(tmp_path))


def test_create_directory(file_manager):
    """Should create a directory if it doesn't exist"""
    test_dir = "test_dir"
    file_manager.create_directory(test_dir)
    assert (file_manager.base_path / test_dir).is_dir()


def test_write_file(file_manager):
    """Should write content to a file"""
    file_path = "test_file.txt"
    content = "Hello, world!"
    file_manager.write_file(file_path, content)
    assert (file_manager.base_path / file_path).read_text() == content


def test_read_file(file_manager):
    """Should read content from a file"""
    file_path = "test_read.txt"
    content = "Read this."
    (file_manager.base_path / file_path).write_text(content)
    read_content = file_manager.read_file(file_path)
    assert read_content == content


def test_delete_file(file_manager):
    """Should delete a file"""
    file_path = "test_delete.txt"
    (file_manager.base_path / file_path).write_text("Delete me.")
    file_manager.delete_file(file_path)
    assert not (file_manager.base_path / file_path).exists()


def test_list_directory_files(file_manager):
    """Should list files in a directory"""
    (file_manager.base_path / "file1.txt").write_text("")
    (file_manager.base_path / "file2.txt").write_text("")
    files = file_manager.list_directory_contents(".")
    assert "file1.txt" in files
    assert "file2.txt" in files


def test_get_absolute_path(file_manager):
    """Should return the absolute path for a given relative path"""
    relative_path = "subdir/file.txt"
    abs_path = file_manager.get_absolute_path(relative_path)
    expected_path = file_manager.base_path / relative_path
    assert abs_path == expected_path.resolve()


def test_delete_file_non_existent(file_manager):
    """Should not raise an error when deleting a non-existent file"""
    file_path = "non_existent_file.txt"
    file_manager.delete_file(file_path)
    assert not (file_manager.base_path / file_path).exists()


def test_delete_directory(file_manager):
    """Should delete a directory and its contents"""
    test_dir = "dir_to_delete"
    (file_manager.base_path / test_dir).mkdir()
    (file_manager.base_path / test_dir / "file.txt").write_text("content")
    file_manager.delete_directory(test_dir)
    assert not (file_manager.base_path / test_dir).exists()


def test_delete_directory_non_existent(file_manager):
    """Should not raise an error when deleting a non-existent directory"""
    test_dir = "non_existent_dir"
    file_manager.delete_directory(test_dir)
    assert not (file_manager.base_path / test_dir).exists()


def test_list_directory_contents_empty(file_manager):
    """Should return an empty list for an empty directory"""
    test_dir = "empty_dir"
    (file_manager.base_path / test_dir).mkdir()
    contents = file_manager.list_directory_contents(test_dir)
    assert contents == []


def test_list_directory_contents_non_existent(file_manager):
    """Should return an empty list for a non-existent directory"""
    test_dir = "non_existent_dir"
    contents = file_manager.list_directory_contents(test_dir)
    assert contents == []


def test_file_exists_true(file_manager):
    """Should return True if the file exists"""
    file_path = "existing_file.txt"
    (file_manager.base_path / file_path).write_text("content")
    assert file_manager.file_exists(file_path) is True


def test_file_exists_false(file_manager):
    """Should return False if the file does not exist"""
    file_path = "non_existing_file.txt"
    assert file_manager.file_exists(file_path) is False


def test_directory_exists_true(file_manager):
    """Should return True if the directory exists"""
    test_dir = "existing_dir"
    (file_manager.base_path / test_dir).mkdir()
    assert file_manager.directory_exists(test_dir) is True


def test_directory_exists_false(file_manager):
    """Should return False if the directory does not exist"""
    test_dir = "non_existing_dir"
    assert file_manager.directory_exists(test_dir) is False
