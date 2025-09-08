import os
import tempfile
from pathlib import Path
from typing import Self

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
    GithubApi,
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
def github_api():
    return mock.Mock(spec=GithubApi)


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
    github_api,
) -> DeploymentMigration:
    return DeploymentMigration(
        version_control=version_control,
        file_handler=file_handler,
        github_actions_author=github_actions_author,
        terraform=terraform_modifier,
        aws=parameter_store,
        application_context=application_context,
        github_api=github_api,
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

    expected_deployment_file = "Never gonna give you up, never gonna let you down"
    github_actions_author.create_deployment_workflow.return_value = (
        expected_deployment_file
    )

    expected_pull_request_file = "Never gonna run around and desert you"
    github_actions_author.create_pull_request_workflow.return_value = (
        expected_pull_request_file
    )

    application.create_github_action_deployment_workflow(
        repository_name="test-app",
        application_name="test-app",
        application_build_tool=ApplicationBuildTool.PYTHON,
        application_runtime_target=ApplicationRuntimeTarget.LAMBDA,
        terraform_base_folder=Path("terraform"),
    )

    assert created_files == {
        Path(".github/workflows/deploy.yml"): expected_deployment_file,
        Path(".github/workflows/pull-request.yml"): expected_pull_request_file,
    }


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


def test_updates_and_writes_terraform_application_resources(
    application: DeploymentMigration,
    file_handler: FileHandler,
    terraform_modifier: Terraform,
) -> None:
    found_module = {
        "github.com/nsbno/terraform-aws-account-metadata": {
            "name": "account_metadata",
        },
    }

    terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
        found_module[module]
    )

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
        terraform_infrastructure_folder="terraform",
    )

    file_to_modify = Path("terraform/main.tf")
    assert written_file == {file_to_modify: terraform_config + expected_file}


def test_update_terraform_application_resources_updates_module_versions(
    application: DeploymentMigration,
    terraform_modifier: Terraform,
) -> None:
    found_module = {
        "github.com/nsbno/terraform-aws-account-metadata": {
            "name": "account_metadata",
        },
    }
    terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
        found_module[module]
    )

    application.upgrade_terraform_application_resources(
        terraform_infrastructure_folder="infrastructure",
    )

    call: mock.call = terraform_modifier.mock_calls[0]
    assert set(call.kwargs["target_modules"].keys()) == {
        "github.com/nsbno/terraform-aws-ecs-service",
        "github.com/nsbno/terraform-aws-lambda",
        "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service",
    }


class TestAWSProviderUpgrade:
    @pytest.fixture(autouse=True)
    def file_handler_data(self: Self, file_handler: FileHandler) -> dict[str, str]:
        files = {
            "infrastructure/versions.tf": "infrastructure_file",
            "environments/test/versions.tf": "test_file",
            "environments/prod/versions.tf": "prod_file",
            "infrastructure/main.tf": "not relevant",
        }
        file_handler.read_file.side_effect = lambda path: files[str(path)]

        return files

    @pytest.fixture(autouse=True)
    def provider_locations(
        self: Self,
        terraform_modifier: Terraform,
        file_handler_data: dict[str, str],
    ) -> dict[str, str]:
        found_provider_spec = {
            f"{file_path.rsplit('/',1)[0]}": {
                "aws": {"file": file_path},
            }
            for file_path in file_handler_data.keys()
            if "main.tf" not in file_path
        }
        terraform_modifier.find_provider.side_effect = (
            lambda provider, folder, *_, **__: (
                found_provider_spec[str(folder)][provider]
            )
        )

    @pytest.fixture(autouse=True)
    def account_metadata_data(self: Self, terraform_modifier: Terraform) -> None:
        found_module = {
            "github.com/nsbno/terraform-aws-account-metadata": {
                "name": "account_metadata",
            },
        }
        terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
            found_module[module]
        )

    def test_updates_aws_provider_version_in_application(
        self: Self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
    ):
        application.upgrade_application_repo_terraform_provider_versions(
            folders=[
                "infrastructure",
                "environments/prod",
                "environments/test",
            ]
        )

        for call in terraform_modifier.update_provider_versions.mock_calls:
            assert call.kwargs["target_providers"] == {"aws": "~> 6.4.0"}

    def test_uses_correct_provider_file_for_provider_upgrade(
        self: Self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        file_handler_data: dict[str, str],
    ):
        application.upgrade_application_repo_terraform_provider_versions(
            folders=[
                "infrastructure",
                "environments/prod",
                "environments/test",
            ]
        )

        calls = terraform_modifier.update_provider_versions.mock_calls
        call_content = [call.args[0] for call in calls]

        for file, content in file_handler_data.items():
            if "main.tf" in file:
                continue
            assert content in call_content

    def test_updates_aws_provider_writes_file_back_to_filesystem(
        self: Self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        file_handler: FileHandler,
        file_handler_data,
    ):
        application.upgrade_application_repo_terraform_provider_versions(
            folders=[
                "infrastructure",
                "environments/prod",
                "environments/test",
            ]
        )

        files_written = [
            call.args[0] for call in file_handler.overwrite_file.mock_calls
        ]
        expected_files = [
            file_name for file_name in file_handler_data if "main.tf" not in file_name
        ]

        assert set(files_written) == set(expected_files)


@pytest.mark.skip("Not Implemented")
class TestUpgradeECSServiceProviderStrategy:
    def test_ecs_service_provider_strategy_gets_upgraded(
        self: Self,
        application: DeploymentMigration,
    ):
        raise NotImplementedError()

    def test_ecs_service_provider_strategy_upgrades_service_in_cluster(self):
        raise NotImplementedError()


class TestAddECRRepository:
    @pytest.fixture(autouse=True)
    def terraform_infra_folder(
        self: Self,
        file_handler: FileHandler,
    ):
        file_handler.folder_exists.return_value = True

        return Path("infrastructure")

    @pytest.fixture(autouse=True)
    def always_find_aws_account_metadata_module(
        self: Self,
        terraform_modifier: Terraform,
    ):
        found_module = {
            "github.com/nsbno/terraform-aws-account-metadata": {
                "name": "account_metadata",
            },
        }

        terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
            found_module[module]
        )

    @pytest.fixture
    def application_name(self: Self) -> str:
        return "test-app"

    @pytest.fixture
    def service_account_id(self: Self) -> str:
        return "23456789012"

    def test_ecr_repository_data_source_is_added_when_not_present(
        self: Self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        application_name: str,
        service_account_id: str,
    ):
        application.replace_image_with_ecr_repository_url(
            "infrastructure", application_name, service_account_id
        )

        call = terraform_modifier.add_data_source.mock_calls[0]

        assert call.args[1] == "aws_ecr_repository"
        assert call.kwargs["name"] == "this"
        assert call.kwargs["variables"] == {
            "name": application_name,
            "registry_id": service_account_id,
        }

    def test_removes_vydev_artifact_reference(
        self: Self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        application_name: str,
        service_account_id: str,
    ):
        application.replace_image_with_ecr_repository_url(
            "infrastructure", application_name, service_account_id
        )

        assert terraform_modifier.remove_vydev_artifact_reference.call_count == 1

    def test_image_reference_on_ecs_service_is_updated_to_ecr_repository(
        self: Self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        application_name: str,
        service_account_id: str,
    ):
        application.replace_image_with_ecr_repository_url(
            "infrastructure", application_name, service_account_id
        )

        assert terraform_modifier.replace_image_tag_on_ecs_module.call_count == 1
        assert (
            terraform_modifier.replace_image_tag_on_ecs_module.mock_calls[0].args[0]
            == "this"
        )


def test_only_finds_environment_folders_in_terraform_infrastructure_folder(
    application: DeploymentMigration,
    file_handler: FileHandler,
) -> None:
    file_handler.get_subfolders.side_effect = [
        ["prod", "staging", "test", "static", "modules", "lol"],
        [],
        [],
    ]

    # Create a tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        # Store the current directory and CD into this temp dir
        current_dir = os.getcwd()
        os.chdir(temp_dir)

        os.mkdir("terraform")

        result = application.find_all_environment_folders()

        os.chdir(current_dir)

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
