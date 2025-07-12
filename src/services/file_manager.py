import os
import shutil

class FileManager:
    def __init__(self, base_path: str):
        self.base_path = base_path

    def get_full_path(self, relative_path: str) -> str:
        """Returns the full absolute path for a given relative path within the base_path."""
        return os.path.join(self.base_path, relative_path)

    def create_directory(self, relative_path: str, exist_ok: bool = True):
        """Creates a directory within the base_path."""
        full_path = self.get_full_path(relative_path)
        os.makedirs(full_path, exist_ok=exist_ok)

    def delete_file(self, relative_path: str):
        """Deletes a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            os.remove(full_path)

    def delete_directory(self, relative_path: str):
        """Deletes a directory and its contents within the base_path."""
        full_path = self.get_full_path(relative_path)
        if os.path.exists(full_path) and os.path.isdir(full_path):
            shutil.rmtree(full_path)

    def list_directory_contents(self, relative_path: str) -> list[str]:
        """Lists the contents of a directory within the base_path."""
        full_path = self.get_full_path(relative_path)
        if os.path.exists(full_path) and os.path.isdir(full_path):
            return os.listdir(full_path)
        return []

    def file_exists(self, relative_path: str) -> bool:
        """Checks if a file exists within the base_path."""
        full_path = self.get_full_path(relative_path)
        return os.path.isfile(full_path)

    def directory_exists(self, relative_path: str) -> bool:
        """Checks if a directory exists within the base_path."""
        full_path = self.get_full_path(relative_path)
        return os.path.isdir(full_path)

    def read_file(self, relative_path: str, mode: str = 'r', encoding: str = 'utf-8'):
        """Reads content from a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        with open(full_path, mode, encoding=encoding) as f:
            return f.read()

    def write_file(self, relative_path: str, content: str, mode: str = 'w', encoding: str = 'utf-8'):
        """Writes content to a file within the base_path."""
        full_path = self.get_full_path(relative_path)
        with open(full_path, mode, encoding=encoding) as f:
            f.write(content)
