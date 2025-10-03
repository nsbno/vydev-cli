"""JSON file-based configuration cache implementation."""

from pathlib import Path
from typing import Self, Optional

from deployment_migration.application import ConfigCache, MigrationConfig


class JsonConfigCache(ConfigCache):
    """JSON file-based configuration cache."""

    CACHE_FILE = ".vydev-cache.json"

    def __init__(self, cache_path: Optional[Path] = None):
        """Initialize cache.

        Args:
            cache_path: Path to cache file (defaults to .vydev-cache.json in cwd)
        """
        self.cache_path = cache_path or Path(self.CACHE_FILE)

    def save_config(self: Self, config: MigrationConfig) -> None:
        """Save configuration to JSON file using Pydantic."""
        try:
            # Pydantic handles all serialization (Enums, datetime, etc.)
            json_str = config.model_dump_json(indent=2)
            with open(self.cache_path, "w") as f:
                f.write(json_str)

        except (OSError, IOError) as e:
            raise RuntimeError(f"Failed to save config cache: {e}")

    def load_config(self: Self) -> Optional[MigrationConfig]:
        """Load configuration from JSON file using Pydantic."""
        if not self.cache_path.exists():
            return None

        try:
            with open(self.cache_path, "r") as f:
                json_str = f.read()

            # Pydantic handles all deserialization and validation
            return MigrationConfig.model_validate_json(json_str)

        except ValueError as e:
            raise RuntimeError(
                f"Config cache file is corrupted: {e}\n"
                f"Run 'rm {self.cache_path}' to clear it."
            )
        except (OSError, IOError) as e:
            raise RuntimeError(f"Failed to load config cache: {e}")

    def clear_config(self: Self) -> None:
        """Delete cache file if it exists."""
        if self.cache_path.exists():
            self.cache_path.unlink()
