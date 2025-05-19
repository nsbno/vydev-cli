from pathlib import Path
from unittest.mock import MagicMock

import pytest

from unittest import mock
from deployment_migration.application import (
    DeploymentMigration,
    VersionControl,
    FileHandler,
    GithubActionsAuthor,
    Terraform,
    AWS,
    ApplicationContext,
    ApplicationRuntimeTarget,
    ApplicationBuildTool,
)


@pytest.fixture
def version_control() -> VersionControl:
    return mock.Mock(spec=VersionControl)


@pytest.fixture
def file_handler() -> FileHandler:
    return mock.Mock(spec=FileHandler)


@pytest.fixture
def github_actions_author() -> GithubActionsAuthor:
    return mock.Mock(spec=GithubActionsAuthor)


@pytest.fixture
def terraform_modifier() -> Terraform:
    return mock.Mock(spec=Terraform)


@pytest.fixture
def parameter_store() -> AWS:
    return mock.Mock(spec=AWS)


@pytest.fixture
def application_context() -> ApplicationContext:
    return mock.Mock(spec=ApplicationContext)


@pytest.fixture
def application(
    version_control,
    file_handler,
    github_actions_author,
    terraform_modifier,
    parameter_store,
    application_context,
) -> DeploymentMigration:
    return DeploymentMigration(
        version_control=version_control,
        file_handler=file_handler,
        github_actions_author=github_actions_author,
        terraform=terraform_modifier,
        aws=parameter_store,
        application_context=application_context,
    )


@pytest.mark.parametrize(
    "folder",
    [
        Path("terraform/template/"),
        Path("terraform/modules/template/"),
        Path("infrastructure/"),
    ],
)
def test_can_find_infrastructure_folder(
    application: DeploymentMigration, file_handler: FileHandler, folder: Path
):
    file_handler.folder_exists.side_effect = lambda x: x == folder

    assert application.find_terraform_infrastructure_folder() == folder
    assert file_handler.folder_exists.call_count >= 1


def test_fails_if_no_infrastructure_folder_is_found(
    application: DeploymentMigration, file_handler: FileHandler
):
    file_handler.folder_exists.return_value = False

    with pytest.raises(FileNotFoundError):
        application.find_terraform_infrastructure_folder()


@pytest.mark.parametrize(
    "folder_base",
    [
        Path("terraform/environment/"),
        Path("environments/"),
    ],
)
@pytest.mark.parametrize(
    "environment_name", ["service", "test", "staging", "production"]
)
def test_can_find_environment_folder(
    application: DeploymentMigration,
    file_handler: FileHandler,
    folder_base: Path,
    environment_name: str,
):
    folder = folder_base / environment_name
    file_handler.folder_exists.side_effect = lambda x: x == folder

    assert application.find_terraform_environment_folder(environment_name) == folder


def test_fails_if_no_environment_folder_is_found(
    application: DeploymentMigration, file_handler: FileHandler
):
    file_handler.folder_exists.return_value = False

    with pytest.raises(FileNotFoundError):
        application.find_terraform_environment_folder("service")


def test_creates_and_writes_github_action_deployment_workflow(
    application: DeploymentMigration,
    file_handler: FileHandler,
    github_actions_author: GithubActionsAuthor,
) -> None:
    created_files = {}
    file_handler.create_file.side_effect = lambda path, content: created_files.update(
        {path: content}
    )

    expected_file = "Never gonna give you up, never gonna let you down"
    github_actions_author.create_deployment_workflow.return_value = expected_file

    application.create_github_action_deployment_workflow(
        application_name="test-app",
        application_build_tool=ApplicationBuildTool.PYTHON,
        application_runtime_target=ApplicationRuntimeTarget.LAMBDA,
        terraform_base_folder=Path("terraform"),
    )

    assert created_files == {Path(".github/workflows/deploy.yml"): expected_file}


def test_upgrades_aws_repo_terraform_resources(
    application: DeploymentMigration,
    file_handler: FileHandler,
    terraform_modifier: Terraform,
) -> None:
    expected_file = "Never gonna give you up, never gonna let you down"
    terraform_modifier.add_module.side_effect = (
        lambda config, *args, **kwargs: config + expected_file
    )

    terraform_config = "We are no strangers to love\nYou know the rules and so do I\n"

    file_handler.read_file.return_value = terraform_config

    written_file = {}
    file_handler.overwrite_file.side_effect = lambda path, content: written_file.update(
        {path: terraform_config + expected_file}
    )

    application.upgrade_aws_repo_terraform_resources(terraform_folder="terraform")

    file_to_modify = Path("terraform/main.tf")
    assert written_file == {file_to_modify: terraform_config + expected_file}


def test_creates_parameter_store_version_parameter(
    application: DeploymentMigration,
    parameter_store: AWS,
) -> None:
    app_name = "test-app"
    temporary_version = "latest"

    parameter_store.find_aws_profile_names.return_value = ["dev-profile"]

    application.create_parameter_store_version_parameter(
        application_name=app_name, temporary_version=temporary_version
    )

    assert parameter_store.create_parameter.mock_calls[0] == mock.call(
        f"/__platform__/versions/{app_name}", temporary_version, "dev-profile"
    )


def test_updates_and_writes_terraform_application_resources(
    application: DeploymentMigration,
    file_handler: FileHandler,
    terraform_modifier: Terraform,
) -> None:
    expected_file = "Never gonna give you up, never gonna let you down"
    terraform_modifier.add_module.side_effect = (
        lambda config, *args, **kwargs: config + expected_file
    )

    terraform_config = "We are no strangers to love\nYou know the rules and so do I\n"

    file_handler.read_file.return_value = terraform_config

    written_file = {}
    file_handler.overwrite_file.side_effect = lambda path, content: written_file.update(
        {path: terraform_config + expected_file}
    )

    application.upgrade_terraform_application_resources(
        terraform_infrastructure_folder="terraform"
    )

    file_to_modify = Path("terraform/main.tf")
    assert written_file == {file_to_modify: terraform_config + expected_file}


def test_update_terraform_application_resources_updates_module_versions(
    application: DeploymentMigration,
    terraform_modifier: Terraform,
) -> None:
    application.upgrade_terraform_application_resources(
        terraform_infrastructure_folder="infrastructure"
    )

    call: mock.call = terraform_modifier.mock_calls[0]
    assert set(call.kwargs["target_modules"].keys()) == {
        "github.com/nsbno/terraform-aws-ecs-service",
        "github.com/nsbno/terraform-aws-lambda",
    }


def test_only_finds_environment_folders_in_terraform_infrastructure_folder(
    application: DeploymentMigration,
    file_handler: FileHandler,
) -> None:
    file_handler.get_subfolders.side_effect = [
        ["prod", "staging", "test", "static", "modules", "lol"],
        [],
        [],
    ]

    result = application.find_all_environment_folders()

    assert result == [Path("prod"), Path("staging"), Path("test")]


def test_remove_old_deployment_setup(
    application: DeploymentMigration,
    file_handler: FileHandler,
) -> None:
    """Test that remove_old_deployment_setup correctly attempts to delete the specified folders."""
    # Call the method
    application.remove_old_deployment_setup()

    # Verify that delete_folder was called for each folder with not_found_ok=True
    assert file_handler.delete_folder.call_count == 2
    file_handler.delete_folder.assert_any_call(Path(".deployment"), not_found_ok=True)
    file_handler.delete_folder.assert_any_call(Path(".circleci"), not_found_ok=True)
