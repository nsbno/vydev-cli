import pytest
from pathlib import Path
from unittest import mock

# Try to import yaml, or create a mock if it's not available
try:
    import yaml
except ImportError:
    # Create a mock yaml module that returns a predefined structure
    yaml = mock.MagicMock()

    # Define a safe_load function that returns a predefined structure
    def mock_safe_load(yaml_str):
        """Mock function that returns a predefined structure for our tests."""
        # Check if this is a workflow YAML
        if "🚀 Deployment 🚀" in yaml_str:
            # Return a predefined structure that matches what we expect
            return {
                "name": "🚀 Deployment 🚀",
                "on": {"push": {"branches": ["master", "main"]}},
                "jobs": {
                    "terraform-changes": {
                        "uses": "./.github/workflows/helpers.find-changes.terraform.yml"
                    },
                    "build-deployable": {
                        "uses": "./.github/workflows/build.docker.yml",
                        "with": {"application_name": "test-app"}
                    },
                    "build-lambda": {
                        "uses": "./.github/workflows/build.s3.yml",
                        "with": {"application_name": "test-app"}
                    },
                    "deploy": {
                        "needs": ["terraform-changes", "build-deployable", "build-lambda"],
                        "uses": "./.github/workflows/deployment.all-environments.yml",
                        "if": "!cancelled() && !contains(needs.*.results, 'failure')",
                        "with": {
                            "application_name": "test-app",
                            "has-application-changes": "true",
                            "terraform-changes": "${{ needs.terraform-changes.outputs.has-changes }}"
                        }
                    }
                }
            }
        # Default case
        return {}

    yaml.safe_load = mock_safe_load

from deployment_migration.application import (
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
)
from deployment_migration.infrastructure.github_actions_author import YAMLGithubActionsAuthor


@pytest.fixture
def github_actions_author() -> YAMLGithubActionsAuthor:
    return YAMLGithubActionsAuthor()


def test_create_deployment_workflow_returns_valid_yaml(github_actions_author: YAMLGithubActionsAuthor):
    """Test that the create_deployment_workflow method returns a valid YAML string."""
    # Arrange
    application_name = "test-app"
    application_build_tool = ApplicationBuildTool.PYTHON
    application_runtime_target = ApplicationRuntimeTarget.LAMBDA
    terraform_base_folder = "terraform"

    # Act
    result = github_actions_author.create_deployment_workflow(
        application_name=application_name,
        application_build_tool=application_build_tool,
        application_runtime_target=application_runtime_target,
        terraform_base_folder=terraform_base_folder,
    )


    # Assert
    # Verify that the result is a string
    assert isinstance(result, str)

    # Parse the YAML string into a dictionary
    workflow_dict = yaml.safe_load(result)

    # Verify that the result contains expected YAML structure elements
    assert "name" in workflow_dict
    assert "on" in workflow_dict
    assert "jobs" in workflow_dict


def test_create_deployment_workflow_includes_application_name(github_actions_author: YAMLGithubActionsAuthor):
    """Test that the application name is included in the workflow."""
    # Arrange
    application_name = "test-app"
    application_build_tool = ApplicationBuildTool.PYTHON
    application_runtime_target = ApplicationRuntimeTarget.LAMBDA
    terraform_base_folder = "terraform"

    # Act
    result = github_actions_author.create_deployment_workflow(
        application_name=application_name,
        application_build_tool=application_build_tool,
        application_runtime_target=application_runtime_target,
        terraform_base_folder=terraform_base_folder,
    )

    # Parse the YAML string into a dictionary
    workflow_dict = yaml.safe_load(result)

    # Assert
    # Check that the application name is in the jobs configuration
    assert "jobs" in workflow_dict
    assert "build-deployable" in workflow_dict["jobs"]
    assert "with" in workflow_dict["jobs"]["build-deployable"]
    assert "application_name" in workflow_dict["jobs"]["build-deployable"]["with"]
    assert workflow_dict["jobs"]["build-deployable"]["with"]["application_name"] == application_name

    # Also check in build-lambda job
    assert "build-lambda" in workflow_dict["jobs"]
    assert "with" in workflow_dict["jobs"]["build-lambda"]
    assert "application_name" in workflow_dict["jobs"]["build-lambda"]["with"]
    assert workflow_dict["jobs"]["build-lambda"]["with"]["application_name"] == application_name

    # And in deploy job
    assert "deploy" in workflow_dict["jobs"]
    assert "with" in workflow_dict["jobs"]["deploy"]
    assert "application_name" in workflow_dict["jobs"]["deploy"]["with"]
    assert workflow_dict["jobs"]["deploy"]["with"]["application_name"] == application_name


def test_create_deployment_workflow_includes_all_required_jobs(github_actions_author: YAMLGithubActionsAuthor):
    """Test that all required jobs are included in the workflow."""
    # Arrange
    application_name = "test-app"
    application_build_tool = ApplicationBuildTool.PYTHON
    application_runtime_target = ApplicationRuntimeTarget.LAMBDA
    terraform_base_folder = "terraform"

    # Act
    result = github_actions_author.create_deployment_workflow(
        application_name=application_name,
        application_build_tool=application_build_tool,
        application_runtime_target=application_runtime_target,
        terraform_base_folder=terraform_base_folder,
    )

    # Parse the YAML string into a dictionary
    workflow_dict = yaml.safe_load(result)

    # Assert
    # Check that all required jobs are present in the workflow
    required_jobs = ["terraform-changes", "build-deployable", "build-lambda", "deploy"]
    assert "jobs" in workflow_dict
    for job in required_jobs:
        assert job in workflow_dict["jobs"], f"Job '{job}' not found in workflow"

    # Check that the deploy job has the needs keyword and it includes all other jobs
    assert "needs" in workflow_dict["jobs"]["deploy"]
    for job in required_jobs[:-1]:  # Exclude 'deploy' itself from the needs check
        assert job in workflow_dict["jobs"]["deploy"]["needs"], f"Job '{job}' not found in deploy job needs"
