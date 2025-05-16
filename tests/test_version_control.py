import pytest
import subprocess
from unittest import mock

from deployment_migration.infrastructure.version_control import GitVersionControl


@pytest.fixture
def version_control() -> GitVersionControl:
    return GitVersionControl()


@pytest.fixture
def mock_subprocess_run():
    """Mock the subprocess.run function."""
    with mock.patch("subprocess.run") as mock_run:
        yield mock_run


def test_commit_adds_and_commits_changes(version_control, mock_subprocess_run):
    """Test that commit adds all changes and commits them with the given message."""
    # Arrange
    commit_message = "Test commit message"

    # Act
    version_control.commit(commit_message)

    # Assert
    # Check that subprocess.run was called twice
    assert mock_subprocess_run.call_count == 2

    # Check the first call (git add .)
    first_call = mock_subprocess_run.call_args_list[0]
    assert first_call[0][0] == ["git", "add", "."]
    assert first_call[1]["check"] is True

    # Check the second call (git commit -m "message")
    second_call = mock_subprocess_run.call_args_list[1]
    assert second_call[0][0] == ["git", "commit", "-m", commit_message]
    assert second_call[1]["check"] is True


def test_commit_handles_git_add_error(version_control, mock_subprocess_run):
    """Test that commit handles errors from git add command."""
    # Arrange
    commit_message = "Test commit message"

    # Set up the mock to raise an exception for git add
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["git", "add", "."], output="fatal: not a git repository"
    )

    # Act & Assert
    with pytest.raises(RuntimeError) as excinfo:
        version_control.commit(commit_message)

    # Check that the error message contains information about the git operation
    assert "Git operation failed" in str(excinfo.value)

    # Check that subprocess.run was called only once (for git add)
    assert mock_subprocess_run.call_count == 1


def test_commit_handles_git_commit_error(version_control, mock_subprocess_run):
    """Test that commit handles errors from git commit command."""
    # Arrange
    commit_message = "Test commit message"

    # Set up the mock to raise an exception for git commit
    mock_subprocess_run.side_effect = [
        None,  # git add succeeds
        subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "commit", "-m", commit_message],
            output="nothing to commit, working tree clean",
        ),
    ]

    # Act & Assert
    with pytest.raises(RuntimeError) as excinfo:
        version_control.commit(commit_message)

    # Check that the error message contains information about the git operation
    assert "Git operation failed" in str(excinfo.value)

    # Check that subprocess.run was called twice (for git add and git commit)
    assert mock_subprocess_run.call_count == 2


def test_commit_with_empty_message(version_control, mock_subprocess_run):
    """Test that commit works with an empty commit message."""
    # Arrange
    commit_message = ""

    # Act
    version_control.commit(commit_message)

    # Assert
    # Check that subprocess.run was called twice
    assert mock_subprocess_run.call_count == 2

    # Check the second call (git commit -m "")
    second_call = mock_subprocess_run.call_args_list[1]
    assert second_call[0][0] == ["git", "commit", "-m", commit_message]


class TestGetOrigin:
    def test_get_origin_http(self, version_control, mock_subprocess_run):
        """Test that get_origin handles HTTP URL format correctly."""
        # Arrange
        mock_subprocess_run.return_value.stdout = "https://github.com/user/repo.git\n"

        # Act
        result = version_control.get_origin()

        # Assert
        assert result == "https://github.com/user/repo"
        mock_subprocess_run.assert_called_once_with(
            ["git", "config", "--get", "remote.origin.url"],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_get_origin_ssh(self, version_control, mock_subprocess_run):
        """Test that get_origin handles SSH URL format correctly."""
        # Arrange
        mock_subprocess_run.return_value.stdout = "git@github.com:user/repo.git\n"

        # Act
        result = version_control.get_origin()

        # Assert
        assert result == "github.com/user/repo"
        mock_subprocess_run.assert_called_once_with(
            ["git", "config", "--get", "remote.origin.url"],
            check=True,
            capture_output=True,
            text=True,
        )
