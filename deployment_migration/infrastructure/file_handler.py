import os
from pathlib import Path
from typing import Self

from deployment_migration.application import FileHandler


class LocalFileHandler(FileHandler):
    """Implementation of FileHandler that interacts with the local filesystem."""

    def create_file(self: Self, path: Path, content: str) -> None:
        """Create a file with the given content at the specified path."""
        # Ensure the directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Write the content to the file
        with open(path, "w") as file:
            file.write(content)

    def read_file(self: Self, path: Path) -> str:
        """Read the content of a file at the specified path."""
        with open(path, "r") as file:
            return file.read()

    def overwrite_file(self: Self, path: Path, content: str) -> None:
        """Overwrite a file with the given content at the specified path."""
        with open(path, "w") as file:
            file.write(content)

    def folder_exists(self: Self, path: Path) -> bool:
        """Check if a folder exists at the specified path."""
        return os.path.isdir(path)

    def get_subfolders(self: Self, path: Path) -> list[Path]:
        return [
            path / folder
            for folder in os.listdir(path)
            if os.path.isdir(os.path.join(path, folder))
        ]

    def delete_folder(self: Self, folder: Path, not_found_ok: bool) -> None:
        """Delete a folder at the specified path."""
        try:
            os.rmdir(folder)
        except FileNotFoundError:
            if not_found_ok:
                return
            raise
