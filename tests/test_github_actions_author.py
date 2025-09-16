import pytest
import yaml

from deployment_migration.application import (
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
)
from deployment_migration.infrastructure.github_actions_author import (
    YAMLGithubActionsAuthor,
)


@pytest.fixture
def github_actions_author() -> YAMLGithubActionsAuthor:
    return YAMLGithubActionsAuthor()


def test_create_deployment_workflow_returns_valid_yaml(
    github_actions_author: YAMLGithubActionsAuthor,
):
    """Test that the create_deployment_workflow method returns a valid YAML string."""
    # Arrange
    application_name = "test-app"
    application_build_tool = ApplicationBuildTool.PYTHON
    application_runtime_target = ApplicationRuntimeTarget.LAMBDA
    terraform_base_folder = "terraform"

    # Act
    result = github_actions_author.create_deployment_workflow(
        repository_name=application_name,
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


def test_create_deployment_workflow_includes_application_name(
    github_actions_author: YAMLGithubActionsAuthor,
):
    """Test that the application name is included in the workflow."""
    # Arrange
    application_name = "test-app"
    application_build_tool = ApplicationBuildTool.PYTHON
    application_runtime_target = ApplicationRuntimeTarget.LAMBDA
    terraform_base_folder = "terraform"

    # Act
    result = github_actions_author.create_deployment_workflow(
        repository_name=application_name,
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
    assert "package" in workflow_dict["jobs"]
    assert "with" in workflow_dict["jobs"]["package"]
    assert "repo-name" in workflow_dict["jobs"]["package"]["with"]
    assert workflow_dict["jobs"]["package"]["with"]["repo-name"] == application_name

    # And in deploy job
    assert "deploy" in workflow_dict["jobs"]
    assert "with" in workflow_dict["jobs"]["deploy"]
    assert "applications" in workflow_dict["jobs"]["deploy"]["with"]
    assert workflow_dict["jobs"]["deploy"]["with"]["applications"] == application_name


def test_create_deployment_workflow_includes_all_required_jobs(
    github_actions_author: YAMLGithubActionsAuthor,
):
    """Test that all required jobs are included in the workflow."""
    # Arrange
    application_name = "test-app"
    application_build_tool = ApplicationBuildTool.PYTHON
    application_runtime_target = ApplicationRuntimeTarget.LAMBDA
    terraform_base_folder = "terraform"

    # Act
    result = github_actions_author.create_deployment_workflow(
        repository_name=application_name,
        application_name=application_name,
        application_build_tool=application_build_tool,
        application_runtime_target=application_runtime_target,
        terraform_base_folder=terraform_base_folder,
    )

    # Parse the YAML string into a dictionary
    workflow_dict = yaml.safe_load(result)

    # Assert
    # Check that all required jobs are present in the workflow
    required_jobs = ["terraform-changes", "build", "package", "deploy"]
    assert "jobs" in workflow_dict
    for job in required_jobs:
        assert job in workflow_dict["jobs"], f"Job '{job}' not found in workflow"

    # Check that the deploy job has the needs keyword and it includes all other jobs
    assert "needs" in workflow_dict["jobs"]["deploy"]
    for job in required_jobs[:-1]:  # Exclude 'deploy' itself from the needs check
        assert (
            job in workflow_dict["jobs"]["deploy"]["needs"]
        ), f"Job '{job}' not found in deploy job needs"


def test_create_deployment_workflow_includes_open_api_upload_if_present(
    github_actions_author: YAMLGithubActionsAuthor,
) -> None:
    application_name = "test-app"
    application_build_tool = ApplicationBuildTool.GRADLE
    application_runtime_target = ApplicationRuntimeTarget.ECS
    terraform_base_folder = "terraform"
    openapi_yaml = "terraform/static/openapi.yaml"

    result = github_actions_author.create_deployment_workflow(
        repository_name=application_name,
        application_name=application_name,
        application_build_tool=application_build_tool,
        application_runtime_target=application_runtime_target,
        terraform_base_folder=terraform_base_folder,
        open_api_spec_path=openapi_yaml,
    )

    workflow_dict = yaml.safe_load(result)

    assert "upload-openapi-spec" in workflow_dict["jobs"]
    assert "build" in workflow_dict["jobs"]["upload-openapi-spec"]["needs"]
    assert "inherit" in workflow_dict["jobs"]["upload-openapi-spec"]["secrets"]

    assert (
        openapi_yaml
        in workflow_dict["jobs"]["upload-openapi-spec"]["with"]["open-api-spec-path"]
    )
