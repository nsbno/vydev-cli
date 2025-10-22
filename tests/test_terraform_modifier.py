from pathlib import Path

import pytest

from deployment_migration.application import Terraform
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


def test_has_module_finds_existing_module(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
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


def test_has_module_finds_module_with_version(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
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


def test_has_module_returns_false_when_module_not_found(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
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


def test_find_module_returns_module_details(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
    """Test that find_module returns the correct module details when a module with the specified source exists."""
    # Arrange
    terraform_config = """
    module "example_module" {
      source = "https://github.com/example/module?ref=1.0.0"
      var1   = "value1"
      var2   = 42
      var3   = true
    }
    """

    # Create a temporary file with the terraform config
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(terraform_config)

    module_source = "https://github.com/example/module"

    # Act
    result = terraform_modifier.find_module(module_source, tmp_path)

    # Assert
    assert result is not None
    assert result["name"] == "example_module"
    assert result["source"] == "https://github.com/example/module?ref=1.0.0"
    assert result["version"] == "1.0.0"
    assert result["variables"]["var1"] == "value1"
    assert result["variables"]["var2"] == "42"  # Note: regex extracts as string
    assert result["variables"]["var3"] == "true"  # Note: regex extracts as string
    assert result["file_path"] == tf_file


def test_find_module_returns_none_when_module_not_found(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
    """Test that find_module returns None when a module with the specified source does not exist."""
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
    result = terraform_modifier.find_module(module_source, tmp_path)

    # Assert
    assert result is None


def test_add_variable_adds_variables_to_existing_module(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that add_variable adds variables to an existing module."""
    # Arrange
    terraform_config = """
    module "example" {
      source = "https://github.com/example/module"
      existing_var = "existing_value"
    }
    """

    target_module = "example"
    variables = {"new_var1": "value1", "new_var2": 42, "new_var3": True}

    # Act
    result = terraform_modifier.add_variable(terraform_config, target_module, variables)

    # Assert
    assert 'module "example"' in result
    assert 'source = "https://github.com/example/module"' in result
    assert 'existing_var = "existing_value"' in result
    assert 'new_var1 = "value1"' in result
    assert "new_var2 = 42" in result
    assert "new_var3 = true" in result


def test_add_variable_raises_error_when_module_not_found(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that add_variable raises an error when the target module is not found."""
    # Arrange
    terraform_config = """
    module "example" {
      source = "https://github.com/example/module"
    }
    """

    target_module = "non_existent_module"
    variables = {"var1": "value1"}

    # Act & Assert
    with pytest.raises(Exception) as excinfo:
        terraform_modifier.add_variable(terraform_config, target_module, variables)

    assert "Could not find module" in str(excinfo.value)


def test_add_test_listener_to_ecs_module(terraform_modifier: RegexTerraformModifier):
    """Test that add_test_listener_to_ecs_module adds the test_listener_arn to the lb_listeners array."""
    # Arrange
    terraform_config = """
    module "github.com/nsbno/terraform-aws-ecs-service" {
      source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0-beta1"
      existing_var = "existing_value"

      lb_listeners = [{
        listener_arn      = "some-listener-arn"
        security_group_id = "some-security-group-id"
        conditions = [{
          path_pattern = "/some-path/*"
        }]
      }]
    }
    """

    metadata_module_name = "account_metadata"

    # Act
    result = terraform_modifier.add_test_listener_to_ecs_module(
        terraform_config, metadata_module_name
    )

    # Assert
    assert 'module "github.com/nsbno/terraform-aws-ecs-service"' in result
    assert (
        'source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0-beta1"'
        in result
    )
    assert 'existing_var = "existing_value"' in result
    assert "lb_listeners = [{" in result
    assert 'listener_arn      = "some-listener-arn"' in result
    assert (
        "      test_listener_arn = module.account_metadata.load_balancer.https_test_listener_arn"
        in result
    )


def test_find_providers_finds_the_correct_folder_with_providers(
    terraform_modifier: RegexTerraformModifier,
    tmp_path: Path,
) -> None:
    """Test that find_module returns None when a module with the specified source does not exist."""
    terraform_config = """
    terraform {
      required_providers {
        aws = {
          source  = "hashicorp/aws"
          version = "~> 4.0.0"
        }
      }
    }
    """
    tf_file = tmp_path / "versions.tf"
    tf_file.write_text(terraform_config)

    result = terraform_modifier.find_provider("aws", tmp_path)

    assert result is not None
    assert result["file"] == tf_file


def test_update_provider_versions_replaces_existing_version(
    terraform_modifier: RegexTerraformModifier,
) -> None:
    """Test that update_provider_versions replaces existing version constraints."""
    # Arrange
    terraform_config = """
    terraform {
      required_providers {
        aws = {
          source  = "hashicorp/aws"
          version = "~> 4.0.0"
        }
      }
    }
    """

    target_providers = {"aws": "~> 6.4.0"}

    # Act
    result = terraform_modifier.update_provider_versions(
        terraform_config, target_providers
    )

    assert 'version = "~> 6.4.0"' in result
    assert 'version = "~> 4.0.0"' not in result
    # Make sure that the amount of lines wasnt changed.
    # Should be a good enough proxy that we didnt add anything.
    assert len(result.splitlines()) == len(terraform_config.splitlines())


def test_add_data_source_adds_datasource(terraform_modifier: Terraform) -> None:
    terraform_config = "// A random comment\n"

    resource_type = "aws_ecr_repository"
    resource_name = "this"
    variables = {"name": "test-repo", "registry_id": "23456789012"}

    result = terraform_modifier.add_data_source(
        terraform_config,
        resource_type,
        resource_name,
        variables,
    )

    assert result == (
        terraform_config
        + "\n"
        + f'data "{resource_type}" "{resource_name}" {{\n'
        + f'  name = "{variables["name"]}"\n'
        + f'  registry_id = "{variables["registry_id"]}"\n'
        + "}\n"
    )


def test_replace_image_tag_on_ecs_module(terraform_modifier: Terraform) -> None:
    terraform_config = (
        'module "github.com/nsbno/terraform-aws-ecs-service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0-beta1"\n'
        '  existing_var = "existing_value"\n'
        '  image = "long long line with a lot of data"\n'
        '  another_existing_var = "existing_value"\n'
        "}"
    )

    result = terraform_modifier.replace_image_tag_on_ecs_module(
        terraform_config, "this"
    )

    expected_config = (
        'module "github.com/nsbno/terraform-aws-ecs-service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0-beta1"\n'
        '  existing_var = "existing_value"\n'
        "    repository_url = data.aws_ecr_repository.this.repository_url\n"
        '  another_existing_var = "existing_value"\n'
        "}"
    )

    assert result == expected_config


def test_remove_vydev_artifacts(terraform_modifier: Terraform) -> None:
    terraform_config = (
        'data "vydev_artifact_version" "this" {\n'
        '  name = "test\n'
        "}\n"
        "\n"
        'data "vydev_cognito_info" "this" {\n'
        '  name = "test\n'
        "}\n"
        "\n"
        'module "github.com/nsbno/terraform-aws-ecs-service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0-beta1"\n'
        '  existing_var = "existing_value"\n'
        '  image = "long long line with a lot of data"\n'
    )

    expected_config = (
        "\n\n"
        'data "vydev_cognito_info" "this" {\n'
        '  name = "test\n'
        "}\n"
        "\n"
        'module "github.com/nsbno/terraform-aws-ecs-service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0-beta1"\n'
        '  existing_var = "existing_value"\n'
        '  image = "long long line with a lot of data"\n'
    )

    updated_config = terraform_modifier.remove_vydev_artifact_reference(
        terraform_config
    )

    assert updated_config == expected_config


def test_has_module_finds_ecs_module_in_main_tf(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
    """Test has_module finds ECS module in template/main.tf (baseline)."""
    terraform_config = (
        'module "ecs_service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0"\n'
        '  name = "my-service"\n'
        "}\n"
    )

    template_dir = tmp_path / "template"
    template_dir.mkdir()
    main_tf = template_dir / "main.tf"
    main_tf.write_text(terraform_config)

    result = terraform_modifier.has_module(
        "github.com/nsbno/terraform-aws-ecs-service", tmp_path
    )

    assert result is True


def test_has_module_finds_ecs_module_in_separate_file(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
    """Test has_module finds ECS module in template/service.tf (not main.tf)."""
    terraform_config = (
        'module "ecs_service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0"\n'
        '  name = "my-service"\n'
        "}\n"
    )

    template_dir = tmp_path / "template"
    template_dir.mkdir()

    # Create main.tf with other content
    main_tf = template_dir / "main.tf"
    main_tf.write_text('resource "aws_s3_bucket" "example" {}\n')

    # Put ECS module in service.tf
    service_tf = template_dir / "service.tf"
    service_tf.write_text(terraform_config)

    result = terraform_modifier.has_module(
        "github.com/nsbno/terraform-aws-ecs-service", tmp_path
    )

    assert result is True


def test_has_module_finds_ecs_module_in_subdirectory(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
    """Test has_module finds ECS module in nested directory structure."""
    terraform_config = (
        'module "ecs_service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0"\n'
        '  name = "my-service"\n'
        "}\n"
    )

    # Create nested structure: template/modules/ecs.tf
    modules_dir = tmp_path / "template" / "modules"
    modules_dir.mkdir(parents=True)

    ecs_tf = modules_dir / "ecs.tf"
    ecs_tf.write_text(terraform_config)

    result = terraform_modifier.has_module(
        "github.com/nsbno/terraform-aws-ecs-service", tmp_path
    )

    assert result is True


def test_has_module_finds_ecs_module_in_service_folder(
    terraform_modifier: RegexTerraformModifier, tmp_path
):
    """Test has_module finds ECS module when in service/ instead of template/."""
    terraform_config = (
        'module "ecs_service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0"\n'
        '  name = "my-service"\n'
        "}\n"
    )

    # Some repos have service/ folder instead of template/
    service_dir = tmp_path / "service"
    service_dir.mkdir()

    main_tf = service_dir / "main.tf"
    main_tf.write_text(terraform_config)

    result = terraform_modifier.has_module(
        "github.com/nsbno/terraform-aws-ecs-service", tmp_path
    )

    assert result is True


def test_add_test_listener_preserves_all_content_with_nested_brackets(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that add_test_listener_to_ecs_module preserves all content when conditions has nested brackets."""
    # Arrange - this is the structure that was causing the issue
    terraform_config = """
    module "github.com/nsbno/terraform-aws-ecs-service" {
      source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0-beta1"
      existing_var = "existing_value"

      lb_listeners = [{
        listener_arn      = local.shared_config.alb_https_listener_arn
        security_group_id = local.shared_config.alb_security_group_id
        conditions = [
          {
            path_pattern = "/${local.base_path}/*"
          }]
      }]

      some_other_var = "should_be_preserved"
    }
    """

    metadata_module_name = "account_metadata"

    # Act
    result = terraform_modifier.add_test_listener_to_ecs_module(
        terraform_config, metadata_module_name
    )

    # Assert - all original content should be preserved
    assert 'module "github.com/nsbno/terraform-aws-ecs-service"' in result
    assert (
        'source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0-beta1"'
        in result
    )
    assert 'existing_var = "existing_value"' in result
    assert "lb_listeners = [{" in result
    assert "listener_arn      = local.shared_config.alb_https_listener_arn" in result
    assert "security_group_id = local.shared_config.alb_security_group_id" in result
    assert 'path_pattern = "/${local.base_path}/*"' in result
    assert (
        "      test_listener_arn = module.account_metadata.load_balancer.https_test_listener_arn"
        in result
    )
    assert 'some_other_var = "should_be_preserved"' in result
    # The closing brackets should be present
    assert result.count("}]") >= 2  # One for conditions, one for lb_listeners


def test_add_force_new_deployment_to_ecs_module(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that add_force_new_deployment_to_ecs_module adds force_new_deployment = true to the ECS module."""
    # Arrange
    terraform_config = """
    module "ecs_service" {
      source = "github.com/nsbno/terraform-aws-ecs-service?ref=3.0.0-rc9"
      existing_var = "existing_value"

      lb_listeners = [{
        listener_arn      = "some-listener-arn"
        security_group_id = "some-security-group-id"
      }]
    }
    """

    # Act
    result = terraform_modifier.add_force_new_deployment_to_ecs_module(terraform_config)

    # Assert
    assert 'module "ecs_service"' in result
    assert (
        'source = "github.com/nsbno/terraform-aws-ecs-service?ref=3.0.0-rc9"' in result
    )
    assert 'existing_var = "existing_value"' in result
    assert "force_new_deployment = true" in result
    assert "lb_listeners = [{" in result  # Ensure existing content is preserved


def test_add_force_new_deployment_raises_error_when_no_ecs_module(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that add_force_new_deployment_to_ecs_module raises NotFoundError when no ECS module exists."""
    # Arrange - config with no ECS module
    terraform_config = """
    module "lambda_function" {
      source = "github.com/nsbno/terraform-aws-lambda?ref=2.0.0"
      function_name = "my-function"
    }
    """

    # Act & Assert
    from deployment_migration.application import NotFoundError

    with pytest.raises(NotFoundError, match="No ECS module was found"):
        terraform_modifier.add_force_new_deployment_to_ecs_module(terraform_config)


def test_add_force_new_deployment_with_nested_blocks(
    terraform_modifier: RegexTerraformModifier,
):
    """Test that force_new_deployment is added at module level, not inside nested blocks."""
    # Arrange - module with nested blocks like datadog_options
    terraform_config = """
module "service" {
  source = "github.com/nsbno/terraform-aws-ecs-service?ref=3.0.0-rc9"
  service_name = "my-service"

  datadog_options = {
    trace_partial_flush_min_spans = 2000
  }

  application_container = {
    name = "my-app"
    port = 8080
  }
}
"""

    # Act
    result = terraform_modifier.add_force_new_deployment_to_ecs_module(terraform_config)

    # Assert - force_new_deployment should be at module level, not inside nested blocks
    assert "force_new_deployment = true" in result

    # Verify the structure is correct - force_new_deployment should be a direct child of module
    lines = result.split("\n")
    force_deployment_line = [
        i for i, line in enumerate(lines) if "force_new_deployment" in line
    ][0]

    # The line should have 2 spaces of indentation (module level)
    assert lines[force_deployment_line].startswith(
        "  force_new_deployment"
    ), f"force_new_deployment should be at module level (2 spaces), got: '{lines[force_deployment_line]}'"

    # Make sure it's NOT indented 4+ spaces (which would indicate it's inside a nested block)
    assert not lines[force_deployment_line].startswith(
        "    force_new_deployment"
    ), "force_new_deployment should not be inside a nested block (4+ spaces)"

    # Verify the nested blocks are still intact and properly formatted
    assert "datadog_options = {" in result
    assert "trace_partial_flush_min_spans = 2000" in result
    assert "application_container = {" in result
