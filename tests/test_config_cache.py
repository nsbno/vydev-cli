"""Tests for configuration caching functionality."""

import tempfile
from pathlib import Path


from deployment_migration.application import (
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
    MigrationConfig,
)
from deployment_migration.infrastructure.config_cache import JsonConfigCache


def test_save_and_load_config():
    """Saved config should be loadable."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_path = Path(tmp_dir) / ".vydev-cache.json"
        cache = JsonConfigCache(cache_path)

        config = MigrationConfig(
            terraform_folder="terraform/template",
            repository_name="my-app",
            application_name="my-app",
            build_tool=ApplicationBuildTool.PYTHON,
            runtime_target=ApplicationRuntimeTarget.ECS,
        )

        cache.save_config(config)
        loaded = cache.load_config()

        assert loaded is not None
        assert loaded.terraform_folder == "terraform/template"
        assert loaded.repository_name == "my-app"
        assert loaded.build_tool == ApplicationBuildTool.PYTHON
        assert loaded.runtime_target == ApplicationRuntimeTarget.ECS


def test_load_returns_none_when_no_cache():
    """Loading non-existent cache should return None."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_path = Path(tmp_dir) / ".vydev-cache.json"
        cache = JsonConfigCache(cache_path)

        loaded = cache.load_config()

        assert loaded is None


def test_clear_config_removes_cache_file():
    """Clearing config should delete cache file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_path = Path(tmp_dir) / ".vydev-cache.json"
        cache = JsonConfigCache(cache_path)

        config = MigrationConfig(
            terraform_folder="terraform",
            repository_name="app",
            application_name="app",
            build_tool=ApplicationBuildTool.GRADLE,
            runtime_target=ApplicationRuntimeTarget.LAMBDA,
        )

        cache.save_config(config)
        assert cache_path.exists()

        cache.clear_config()
        assert not cache_path.exists()
