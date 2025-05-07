import subprocess
from typing import Self

from deployment_migration.application import VersionControl


class GitVersionControl(VersionControl):
    """Implementation of VersionControl that interacts with Git."""

    def commit(self: Self, message: str) -> None:
        """Commit changes to the Git repository with the given message."""
        try:
            # Add all changes
            subprocess.run(["git", "add", "."], check=True)

            # Commit with the provided message
            subprocess.run(["git", "commit", "-m", message], check=True)
        except subprocess.CalledProcessError as e:
            # Handle git command errors
            raise RuntimeError(f"Git operation failed: {e}")
