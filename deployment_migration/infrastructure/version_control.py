import subprocess
from typing import Self

from deployment_migration.application import VersionControl


class GitVersionControl(VersionControl):
    """Implementation of VersionControl that interacts with Git."""

    def get_origin(self: Self) -> str:
        """Get the remote origin URL of the Git repository."""
        try:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                check=True,
                capture_output=True,
                text=True,
            )

            origin_url = result.stdout.strip()

            if origin_url.endswith(".git"):
                origin_url = origin_url[:-4]

            if origin_url.startswith("git@github.com:"):
                origin_url = origin_url.replace("git@github.com:", "github.com/")

            return origin_url

        except subprocess.CalledProcessError as e:
            raise RuntimeError("Failed to get Git origin URL: " + str(e))

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

    def push(self: Self):
        """Push changes to the remote Git repository."""
        try:
            subprocess.run(["git", "push"], check=True)
        except subprocess.CalledProcessError as e:
            # Handle git command errors
            raise RuntimeError(f"Git operation failed: {e}")
