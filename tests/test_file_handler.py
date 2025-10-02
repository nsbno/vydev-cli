import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from deployment_migration.infrastructure.file_handler import LocalFileHandler


@pytest.fixture
def file_handler() -> LocalFileHandler:
    return LocalFileHandler()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for file operations."""
    with TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def test_create_file_creates_file_with_content(
    file_handler: LocalFileHandler, temp_dir: Path
):
    """Test that create_file creates a file with the specified content."""
    # Arrange
    test_file = temp_dir / "test_file.txt"
    test_content = "Test content"

    # Act
    file_handler.create_file(test_file, test_content)

    # Assert
    assert test_file.exists()
    with open(test_file, "r") as f:
        assert f.read() == test_content


def test_create_file_creates_directories_if_needed(
    file_handler: LocalFileHandler, temp_dir: Path
):
    """Test that create_file creates directories if they don't exist."""
    # Arrange
    nested_dir = temp_dir / "nested" / "directory"
    test_file = nested_dir / "test_file.txt"
    test_content = "Test content"

    # Act
    file_handler.create_file(test_file, test_content)

    # Assert
    assert test_file.exists()
    with open(test_file, "r") as f:
        assert f.read() == test_content


def test_read_file_returns_file_content(file_handler: LocalFileHandler, temp_dir: Path):
    """Test that read_file returns the content of the specified file."""
    # Arrange
    test_file = temp_dir / "test_file.txt"
    test_content = "Test content"

    # Create the file directly
    with open(test_file, "w") as f:
        f.write(test_content)

    # Act
    result = file_handler.read_file(test_file)

    # Assert
    assert result == test_content


def test_overwrite_file_overwrites_existing_file(
    file_handler: LocalFileHandler, temp_dir: Path
):
    """Test that overwrite_file overwrites an existing file with the specified content."""
    # Arrange
    test_file = temp_dir / "test_file.txt"
    initial_content = "Initial content"
    new_content = "New content"

    # Create the file with initial content
    with open(test_file, "w") as f:
        f.write(initial_content)

    # Act
    file_handler.overwrite_file(test_file, new_content)

    # Assert
    with open(test_file, "r") as f:
        assert f.read() == new_content


def test_folder_exists_returns_true_for_existing_folder(
    file_handler: LocalFileHandler, temp_dir: Path
):
    """Test that folder_exists returns True for an existing folder."""
    # Arrange
    test_folder = temp_dir / "test_folder"
    os.makedirs(test_folder, exist_ok=True)

    # Act
    result = file_handler.folder_exists(test_folder)

    # Assert
    assert result is True


def test_folder_exists_returns_false_for_nonexistent_folder(
    file_handler: LocalFileHandler, temp_dir: Path
):
    """Test that folder_exists returns False for a nonexistent folder."""
    # Arrange
    test_folder = temp_dir / "nonexistent_folder"

    # Act
    result = file_handler.folder_exists(test_folder)

    # Assert
    assert result is False


def test_folder_exists_returns_false_for_file(
    file_handler: LocalFileHandler, temp_dir: Path
):
    """Test that folder_exists returns False for a file."""
    # Arrange
    test_file = temp_dir / "test_file.txt"
    with open(test_file, "w") as f:
        f.write("Test content")

    # Act
    result = file_handler.folder_exists(test_file)

    # Assert
    assert result is False
