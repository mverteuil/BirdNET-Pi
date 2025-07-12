import pytest

from services.file_manager import FileManager


@pytest.fixture
def file_manager(tmp_path):
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
