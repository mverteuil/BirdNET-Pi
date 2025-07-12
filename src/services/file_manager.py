import shutil
from pathlib import Path


class FileManager:
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)

    def get_full_path(self, relative_path: str) -> Path:
        """Returns the full absolute Path for a given relative path within the base_path."""
        return self.base_path / relative_path

    def get_absolute_path(self, relative_path: str) -> Path:
        """Returns the absolute Path for a given relative path within the base_path."""
        return self.get_full_path(relative_path).resolve()

    def create_directory(self, relative_path: str, exist_ok: bool = True):
        """Creates a directory within the base_path."""
        full_path = self.get_full_path(relative_path)
        full_path.mkdir(parents=True, exist_ok=exist_ok)

    def delete_file(self, relative_path: str):
        """Deletes a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        if full_path.is_file():
            full_path.unlink()

    def delete_directory(self, relative_path: str):
        """Deletes a directory and its contents within the base_path."""
        full_path = self.get_full_path(relative_path)
        if full_path.is_dir():
            shutil.rmtree(full_path)

    def list_directory_contents(self, relative_path: str) -> list[str]:
        """Lists the contents of a directory within the base_path."""
        full_path = self.get_full_path(relative_path)
        if full_path.is_dir():
            return [str(p.name) for p in full_path.iterdir()]
        return []

    def file_exists(self, relative_path: str) -> bool:
        """Checks if a file exists within the base_path."""
        full_path = self.get_full_path(relative_path)
        return full_path.is_file()

    def directory_exists(self, relative_path: str) -> bool:
        """Checks if a directory exists within the base_path."""
        full_path = self.get_full_path(relative_path)
        return full_path.is_dir()

    def read_file(self, relative_path: str, mode: str = "r", encoding: str = "utf-8"):
        """Reads content from a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        return full_path.read_text(encoding=encoding)

    def write_file(
        self, relative_path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ):
        """Writes content to a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        full_path.write_text(content, encoding=encoding)
