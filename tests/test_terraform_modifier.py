import pytest
from typing import Dict, Any

from deployment_migration.infrastructure.terraform_modifier import (
    RegexTerraformModifier,
)


@pytest.fixture
def terraform_modifier() -> RegexTerraformModifier:
    return RegexTerraformModifier()


def test_update_module_versions_updates_existing_version(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that update_module_versions updates the version of an existing module."""
    # Arrange
    terraform_config = """
    module "example" {
      source  = "https://github.com/example/module?ref=1.0.0"
    }
    """

    target_modules = {"https://github.com/example/module": "2.0.0"}

    # Act
    result = terraform_modifier.update_module_versions(terraform_config, target_modules)

    # Assert
    assert 'source  = "https://github.com/example/module?ref=2.0.0"' in result
    assert 'source  = "https://github.com/example/module?ref=1.0.0"' not in result


def test_update_module_versions_adds_version_if_missing(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that update_module_versions adds a version to the source URL if it's missing."""
    # Arrange
    terraform_config = """
    module "example" {
      source = "https://github.com/example/module"
    }
    """

    target_modules = {"https://github.com/example/module": "2.0.0"}

    # Act
    result = terraform_modifier.update_module_versions(terraform_config, target_modules)

    # Assert
    assert 'source = "https://github.com/example/module?ref=2.0.0"' in result
    assert 'source = "https://github.com/example/module"' not in result


def test_update_module_versions_handles_multiple_modules(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that update_module_versions handles multiple modules correctly."""
    # Arrange
    terraform_config = """
    module "example1" {
      source  = "https://github.com/example/module1?ref=1.0.0"
    }

    module "example2" {
      source = "https://github.com/example/module2"
    }
    """

    target_modules = {
        "https://github.com/example/module1": "2.0.0",
        "https://github.com/example/module2": "3.0.0",
    }

    # Act
    result = terraform_modifier.update_module_versions(terraform_config, target_modules)

    # Assert
    assert 'source  = "https://github.com/example/module1?ref=2.0.0"' in result
    assert 'source = "https://github.com/example/module2?ref=3.0.0"' in result
    assert 'source  = "https://github.com/example/module1?ref=1.0.0"' not in result
    assert 'source = "https://github.com/example/module2"' not in result


def test_add_module_creates_module_block(terraform_modifier: RegexTerraformModifier):
    """Test that add_module creates a module block with the specified parameters."""
    terraform_config = """
    provider "aws" {
      region = "eu-west-1"
    }
    """

    name = "new_module"
    source = "https://github.com/example/module"
    version = "1.0.0"
    variables = {"var1": "value1", "var2": 42, "var3": True}

    result = terraform_modifier.add_module(
        terraform_config=terraform_config,
        name=name,
        source=source,
        version=version,
        variables=variables,
    )

    assert f'module "{name}"' in result
    assert f'source = "{source}?ref={version}"' in result
    assert 'var1 = "value1"' in result
    assert "var2 = 42" in result
    assert "var3 = true" in result


def test_add_module_without_version(terraform_modifier: RegexTerraformModifier):
    """Test that add_module works correctly without a version."""
    # Arrange
    terraform_config = """
    provider "aws" {
      region = "eu-west-1"
    }
    """

    name = "new_module"
    source = "https://github.com/example/module"

    # Act
    result = terraform_modifier.add_module(
        terraform_config=terraform_config,
        name=name,
        source=source,
        version="",
        variables={},
    )

    # Assert
    assert f'module "{name}"' in result
    assert f'source = "{source}"' in result
    assert "?ref=" not in result


def test_add_module_without_variables(terraform_modifier: RegexTerraformModifier):
    """Test that add_module works correctly without variables."""
    # Arrange
    terraform_config = """
    provider "aws" {
      region = "eu-west-1"
    }
    """

    name = "new_module"
    source = "https://github.com/example/module"
    version = "1.0.0"

    # Act
    result = terraform_modifier.add_module(
        terraform_config=terraform_config,
        name=name,
        source=source,
        version=version,
        variables=None,
    )

    # Assert
    assert f'module "{name}"' in result
    assert f'source = "{source}?ref={version}"' in result
    # Check that there are no variable assignments
    assert "\n  var" not in result


def test_has_module_finds_existing_module(terraform_modifier: RegexTerraformModifier, tmp_path):
    """Test that has_module returns True when a module with the specified source exists."""
    # Arrange
    terraform_config = """
    module "example" {
      source = "https://github.com/example/module"
    }
    """

    # Create a temporary file with the terraform config
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(terraform_config)

    module_source = "https://github.com/example/module"

    # Act
    result = terraform_modifier.has_module(module_source, tmp_path)

    # Assert
    assert result is True


def test_has_module_finds_module_with_version(terraform_modifier: RegexTerraformModifier, tmp_path):
    """Test that has_module returns True when a module with the specified source and a version exists."""
    # Arrange
    terraform_config = """
    module "example" {
      source = "https://github.com/example/module?ref=1.0.0"
    }
    """

    # Create a temporary file with the terraform config
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(terraform_config)

    module_source = "https://github.com/example/module"

    # Act
    result = terraform_modifier.has_module(module_source, tmp_path)

    # Assert
    assert result is True


def test_has_module_returns_false_when_module_not_found(terraform_modifier: RegexTerraformModifier, tmp_path):
    """Test that has_module returns False when a module with the specified source does not exist."""
    # Arrange
    terraform_config = """
    module "example" {
      source = "https://github.com/example/other-module"
    }
    """

    # Create a temporary file with the terraform config
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(terraform_config)

    module_source = "https://github.com/example/module"

    # Act
    result = terraform_modifier.has_module(module_source, tmp_path)

    # Assert
    assert result is False
