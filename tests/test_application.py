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
    file_handler.read_file.return_value = "workflows: {}"

    expected_deployment_file = "Never gonna give you up, never gonna let you down"
    github_actions_author.create_deployment_workflow.return_value = (
        expected_deployment_file
    )

    expected_pull_request_file = "Never gonna run around and desert you"
    github_actions_author.create_pull_request_workflow.return_value = (
        expected_pull_request_file
    )

    expected_pull_request_comment_file = (
        "Never gonna make you cry, never gonna say goodbye"
    )
    github_actions_author.create_pull_request_comment_workflow.return_value = (
        expected_pull_request_comment_file
    )

    application.create_github_action_deployment_workflow(
        repository_name="test-app",
        application_name="test-app",
        application_build_tool=ApplicationBuildTool.PYTHON,
        application_runtime_target=ApplicationRuntimeTarget.LAMBDA,
        terraform_base_folder=Path("terraform"),
    )

    assert created_files == {
        Path(".github/workflows/build-and-deploy.yml"): expected_deployment_file,
        Path(".github/workflows/pull-request.yml"): expected_pull_request_file,
        Path(
            ".github/workflows/pull-request-comment.yml"
        ): expected_pull_request_comment_file,
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
    # Mock find_module to return None (module doesn't exist yet)
    terraform_modifier.find_module.return_value = None

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
        "github.com/nsbno/terraform-aws-ecs-service": {
            "name": "ecs",
            "file_path": Path("terraform/main.tf"),
        },
        "github.com/nsbno/terraform-aws-lambda": None,
        "github.com/nsbno/terraform-aws-account-metadata": {
            "name": "account_metadata",
            "file_path": Path("terraform/main.tf"),
        },
        "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service": None,
    }

    terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
        found_module.get(module)
    )
    terraform_modifier.has_module.return_value = False  # No ECS or Spring Boot module

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
        "github.com/nsbno/terraform-aws-ecs-service": {
            "name": "ecs",
            "file_path": Path("terraform/main.tf"),
        },
        "github.com/nsbno/terraform-aws-lambda": None,
        "github.com/nsbno/terraform-aws-account-metadata": {
            "name": "account_metadata",
            "file_path": Path("terraform/main.tf"),
        },
        "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service": None,
    }
    terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
        found_module.get(module)
    )
    terraform_modifier.has_module.return_value = False  # No ECS or Spring Boot module

    application.upgrade_terraform_application_resources(
        terraform_infrastructure_folder="infrastructure",
    )

    # With new multi-file design, update_module_versions is called once per module
    # Collect all modules that were updated
    update_calls = [
        call
        for call in terraform_modifier.mock_calls
        if call[0] == "update_module_versions"
    ]

    # Get all modules that were attempted to be updated
    updated_modules = set()
    for call in update_calls:
        updated_modules.update(call.kwargs["target_modules"].keys())

    # Only modules that exist (have file_path) should be updated
    assert updated_modules == {
        "github.com/nsbno/terraform-aws-ecs-service",
        "github.com/nsbno/terraform-aws-account-metadata",
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
            assert call.kwargs["target_providers"] == {"aws": ">= 6.15.0, < 7.0.0"}

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
            "github.com/nsbno/terraform-aws-ecs-service": {
                "name": "ecs",
                "file_path": Path("infrastructure/main.tf"),
            },
            "github.com/nsbno/terraform-aws-account-metadata": {
                "name": "account_metadata",
            },
        }

        terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
            found_module.get(module)
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
            terraform_modifier.replace_image_tag_on_ecs_module.mock_calls[0].args[1]
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
    """Test that remove_old_deployment_setup deletes .deployment, lock files, and replaces .circleci/config.yml with no-op."""
    # Expected no-op CircleCI config
    expected_circleci_config = (
        "version: 2.1\n"
        "\n"
        "jobs:\n"
        "  no_op:\n"
        "    type: no-op\n"
        "\n"
        "workflows:\n"
        "  no_op_workflow:\n"
        "    jobs: [no_op]\n"
    )

    # Mock finding terraform lock files
    mock_lock_files = [
        Path("terraform/template/.terraform.lock.hcl"),
        Path("terraform/dev/.terraform.lock.hcl"),
        Path("terraform/prod/.terraform.lock.hcl"),
    ]
    file_handler.find_files_by_pattern.return_value = mock_lock_files

    # Call the method
    application.remove_old_deployment_setup()

    # Verify that .deployment folder is deleted
    file_handler.delete_folder.assert_called_once_with(
        Path(".deployment"), not_found_ok=True
    )

    # Verify that terraform lock files are found and deleted
    file_handler.find_files_by_pattern.assert_called_once_with(
        ".terraform.lock.hcl", Path(".")
    )

    # Verify each lock file is deleted
    assert file_handler.delete_file.call_count == len(mock_lock_files)
    for lock_file in mock_lock_files:
        file_handler.delete_file.assert_any_call(lock_file, not_found_ok=True)

    # Verify that .circleci/config.yml is overwritten with no-op config
    file_handler.overwrite_file.assert_called_once_with(
        Path(".circleci/config.yml"), expected_circleci_config
    )


def test_remove_old_deployment_setup_handles_no_lock_files(
    application: DeploymentMigration,
    file_handler: FileHandler,
) -> None:
    """Test that remove_old_deployment_setup handles case when no terraform lock files exist."""
    # Expected no-op CircleCI config
    expected_circleci_config = (
        "version: 2.1\n"
        "\n"
        "jobs:\n"
        "  no_op:\n"
        "    type: no-op\n"
        "\n"
        "workflows:\n"
        "  no_op_workflow:\n"
        "    jobs: [no_op]\n"
    )

    # Mock finding no terraform lock files
    file_handler.find_files_by_pattern.return_value = []

    # Call the method - should not raise any errors
    application.remove_old_deployment_setup()

    # Verify that .deployment folder is deleted
    file_handler.delete_folder.assert_called_once_with(
        Path(".deployment"), not_found_ok=True
    )

    # Verify that terraform lock files search was performed
    file_handler.find_files_by_pattern.assert_called_once_with(
        ".terraform.lock.hcl", Path(".")
    )

    # Verify no delete_file calls were made (no lock files to delete)
    file_handler.delete_file.assert_not_called()

    # Verify that .circleci/config.yml is overwritten with no-op config
    file_handler.overwrite_file.assert_called_once_with(
        Path(".circleci/config.yml"), expected_circleci_config
    )


def test_find_openapi_spec_returns_path_when_circleci_config_exists_with_spec(
    application: DeploymentMigration,
    file_handler: FileHandler,
) -> None:
    """Test _find_openapi_spec returns OpenAPI spec path from .circleci/config.yml."""
    circleci_config = (
        "workflows:\n"
        "  deploy:\n"
        "    jobs:\n"
        "      - documentation/push-api-spec:\n"
        '          openapi-path: "src/main/resources/openapi.yaml"\n'
    )
    file_handler.read_file.return_value = circleci_config

    result = application._find_openapi_spec()

    assert result == Path("src/main/resources/openapi.yaml")
    file_handler.read_file.assert_called_once_with(Path(".circleci/config.yml"))


def test_find_open_api_spec_handles_other_non_workflow_jobs(
    application: DeploymentMigration,
    file_handler: FileHandler,
) -> None:
    """Test _find_openapi_spec handles other non-workflow jobs."""
    circleci_config = (
        "workflows:\n"
        "  version: 2\n"
        "  deploy:\n"
        "    jobs:\n"
        "      - documentation/push-api-spec:\n"
        '          openapi-path: "src/main/resources/openapi.yaml"\n'
    )
    file_handler.read_file.return_value = circleci_config

    result = application._find_openapi_spec()

    assert result == Path("src/main/resources/openapi.yaml")
    file_handler.read_file.assert_called_once_with(Path(".circleci/config.yml"))


def test_find_openapi_spec_returns_none_when_circleci_config_exists_without_spec(
    application: DeploymentMigration,
    file_handler: FileHandler,
) -> None:
    """Test _find_openapi_spec returns None when config exists without OpenAPI spec."""
    circleci_config = (
        "workflows:\n" "  deploy:\n" "    jobs:\n" "      - build\n" "      - test\n"
    )
    file_handler.read_file.return_value = circleci_config

    result = application._find_openapi_spec()

    assert result is None
    file_handler.read_file.assert_called_once_with(Path(".circleci/config.yml"))


def test_find_openapi_spec_returns_none_when_circleci_folder_does_not_exist(
    application: DeploymentMigration,
    file_handler: FileHandler,
) -> None:
    """Test _find_openapi_spec returns None when .circleci folder doesn't exist.

    Instead of crashing with FileNotFoundError, the method should return None
    to allow the migration to continue gracefully.
    """
    file_handler.read_file.side_effect = FileNotFoundError(
        ".circleci/config.yml not found"
    )

    result = application._find_openapi_spec()

    assert result is None
    file_handler.read_file.assert_called_once_with(Path(".circleci/config.yml"))


def test_upgrade_terraform_application_resources_with_ecs_in_separate_file(
    application: DeploymentMigration,
    file_handler: FileHandler,
    terraform_modifier: Terraform,
) -> None:
    """Test upgrade works when ECS module is in service.tf, not main.tf."""
    # Module is in service.tf
    terraform_modifier.find_module.return_value = {
        "name": "ecs_service",
        "file_path": Path("terraform/template/service.tf"),
        "source": "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0",
    }
    # has_module returns True only for ECS module, not Spring Boot
    terraform_modifier.has_module.side_effect = (
        lambda module, *_: module == "github.com/nsbno/terraform-aws-ecs-service"
    )

    service_tf_content = (
        'module "ecs_service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0"\n'
        "}\n"
    )
    file_handler.read_file.return_value = service_tf_content
    terraform_modifier.update_module_versions.return_value = service_tf_content.replace(
        "2.0.0", "3.0.0-rc3"
    )
    terraform_modifier.add_test_listener_to_ecs_module.return_value = (
        service_tf_content.replace("2.0.0", "3.0.0-rc3")
    )
    terraform_modifier.add_force_new_deployment_to_ecs_module.return_value = (
        service_tf_content.replace("2.0.0", "3.0.0-rc3")
    )

    written_files = {}
    file_handler.overwrite_file.side_effect = lambda path, content: (
        written_files.update({str(path): content})
    )

    application.upgrade_terraform_application_resources("terraform/template")

    # Should write to service.tf, NOT main.tf
    assert "terraform/template/service.tf" in written_files
    assert "3.0.0-rc3" in written_files["terraform/template/service.tf"]


def test_replace_image_with_ecr_when_ecs_in_separate_file(
    application: DeploymentMigration,
    file_handler: FileHandler,
    terraform_modifier: Terraform,
) -> None:
    """Test image replacement works when ECS module is in ecs.tf, not main.tf."""
    terraform_modifier.find_module.return_value = {
        "name": "ecs_service",
        "file_path": Path("terraform/template/ecs.tf"),
        "source": "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0",
    }

    ecs_tf_content = (
        'module "ecs_service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0"\n'
        '  image = "old-image"\n'
        "}\n"
    )
    file_handler.read_file.return_value = ecs_tf_content

    terraform_modifier.add_data_source.return_value = (
        'data "aws_ecr_repository" "this" {}\n' + ecs_tf_content
    )
    terraform_modifier.remove_vydev_artifact_reference.return_value = (
        'data "aws_ecr_repository" "this" {}\n' + ecs_tf_content
    )
    terraform_modifier.replace_image_tag_on_ecs_module.return_value = (
        'data "aws_ecr_repository" "this" {}\n'
        'module "ecs_service" {\n'
        "  repository_url = data.aws_ecr_repository.this.repository_url\n"
        "}\n"
    )

    written_files = {}
    file_handler.overwrite_file.side_effect = lambda path, content: (
        written_files.update({str(path): content})
    )

    application.replace_image_with_ecr_repository_url(
        "terraform/template", "my-repo", "123456789"
    )

    # Should write to ecs.tf, NOT main.tf
    assert "terraform/template/ecs.tf" in written_files
    assert "repository_url" in written_files["terraform/template/ecs.tf"]


def test_upgrade_terraform_application_adds_force_new_deployment(
    application: DeploymentMigration,
    file_handler: FileHandler,
    terraform_modifier: Terraform,
) -> None:
    """Test that upgrade_terraform_application_resources adds force_new_deployment to ECS module."""
    # Setup: ECS module exists
    # has_module returns True only for ECS module, not Spring Boot
    terraform_modifier.has_module.side_effect = (
        lambda module, *_: module == "github.com/nsbno/terraform-aws-ecs-service"
    )
    terraform_modifier.find_module.side_effect = lambda source, folder: {
        "github.com/nsbno/terraform-aws-ecs-service": {
            "name": "ecs_service",
            "file_path": Path("terraform/template/service.tf"),
            "source": "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0",
        },
        "github.com/nsbno/terraform-aws-account-metadata": {
            "name": "metadata",
            "file_path": Path("terraform/template/main.tf"),
            "source": "github.com/nsbno/terraform-aws-account-metadata?ref=0.5.0",
        },
    }.get(source)

    service_tf_content = (
        'module "ecs_service" {\n'
        '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0"\n'
        "}\n"
    )
    file_handler.read_file.return_value = service_tf_content
    terraform_modifier.update_module_versions.return_value = service_tf_content.replace(
        "2.0.0", "3.0.0-rc9"
    )
    terraform_modifier.add_test_listener_to_ecs_module.return_value = (
        service_tf_content.replace("2.0.0", "3.0.0-rc9")
    )
    terraform_modifier.add_force_new_deployment_to_ecs_module.return_value = (
        service_tf_content.replace("2.0.0", "3.0.0-rc9")
        + "  force_new_deployment = true\n"
    )

    application.upgrade_terraform_application_resources("terraform/template")

    # Verify that add_force_new_deployment_to_ecs_module was called
    terraform_modifier.add_force_new_deployment_to_ecs_module.assert_called_once()


def test_upgrade_aws_repo_when_oidc_module_in_separate_file(
    application: DeploymentMigration,
    file_handler: FileHandler,
    terraform_modifier: Terraform,
) -> None:
    """Test AWS repo upgrade works when OIDC module is in github.tf, not main.tf."""
    terraform_modifier.find_module.return_value = {
        "name": "github_actions_oidc",
        "file_path": Path("terraform/service/github.tf"),
        "source": "github.com/nsbno/terraform-aws-github-oidc?ref=0.0.1",
    }
    terraform_modifier.has_module.return_value = True

    github_tf_content = (
        'module "github_actions_oidc" {\n'
        '  source = "github.com/nsbno/terraform-aws-github-oidc?ref=0.0.1"\n'
        "}\n"
    )
    file_handler.read_file.return_value = github_tf_content
    terraform_modifier.update_module_versions.return_value = github_tf_content.replace(
        "0.0.1", "0.1.0"
    )

    written_files = {}
    file_handler.overwrite_file.side_effect = lambda path, content: (
        written_files.update({str(path): content})
    )

    application.upgrade_aws_repo_terraform_resources("terraform/service")

    # Should write to github.tf, NOT main.tf
    assert "terraform/service/github.tf" in written_files
    assert "0.1.0" in written_files["terraform/service/github.tf"]


def test_upgrade_terraform_resources_with_modules_in_multiple_files(
    application: DeploymentMigration,
    file_handler: FileHandler,
    terraform_modifier: Terraform,
) -> None:
    """Test that modules spread across multiple files all get updated correctly.

    Scenario:
    - ECS module in ecs.tf
    - Lambda module in lambda.tf
    - Account metadata in main.tf
    - All should be updated in their respective files
    """
    # Mock find_module to return different files for different modules
    module_locations = {
        "github.com/nsbno/terraform-aws-ecs-service": {
            "name": "ecs",
            "file_path": Path("terraform/template/ecs.tf"),
        },
        "github.com/nsbno/terraform-aws-lambda": {
            "name": "lambda",
            "file_path": Path("terraform/template/lambda.tf"),
        },
        "github.com/nsbno/terraform-aws-account-metadata": {
            "name": "metadata",
            "file_path": Path("terraform/template/main.tf"),
        },
    }
    terraform_modifier.find_module.side_effect = lambda module, *_: (
        module_locations.get(module)
    )
    # has_module returns True only for ECS module, not Spring Boot
    terraform_modifier.has_module.side_effect = (
        lambda module, *_: module == "github.com/nsbno/terraform-aws-ecs-service"
    )

    # Mock file contents for each file (mutable dict that gets updated)
    file_contents = {
        Path("terraform/template/ecs.tf"): (
            'module "ecs" {\n'
            '  source = "github.com/nsbno/terraform-aws-ecs-service?ref=2.0.0"\n'
            "}\n"
        ),
        Path("terraform/template/lambda.tf"): (
            'module "lambda" {\n'
            '  source = "github.com/nsbno/terraform-aws-lambda?ref=1.0.0"\n'
            "}\n"
        ),
        Path("terraform/template/main.tf"): (
            'module "metadata" {\n'
            '  source = "github.com/nsbno/terraform-aws-account-metadata?ref=0.4.0"\n'
            "}\n"
        ),
    }

    # read_file returns current content from file_contents
    file_handler.read_file.side_effect = lambda path: file_contents[path]

    # Mock update_module_versions to return updated content
    def mock_update(content, target_modules):
        import re

        for module_source, new_version in target_modules.items():
            if module_source in content:
                # Use regex to replace the version after ?ref=
                module_name = module_source.split("/")[-1]
                pattern = f'{module_name}\\?ref=[^"\\s]+'
                replacement = f"{module_name}?ref={new_version}"
                content = re.sub(pattern, replacement, content)
        return content

    terraform_modifier.update_module_versions.side_effect = mock_update
    terraform_modifier.add_test_listener_to_ecs_module.side_effect = (
        lambda config, **_: config
    )
    terraform_modifier.add_force_new_deployment_to_ecs_module.side_effect = (
        lambda config: config
    )

    written_files = {}

    def mock_overwrite(path, content):
        written_files[path] = content
        # Also update file_contents so subsequent reads get the updated content
        file_contents[path] = content

    file_handler.overwrite_file.side_effect = mock_overwrite

    application.upgrade_terraform_application_resources("terraform/template")

    # All three files should be updated
    assert Path("terraform/template/ecs.tf") in written_files
    assert Path("terraform/template/lambda.tf") in written_files
    assert Path("terraform/template/main.tf") in written_files

    # Each file should have the correct version
    assert "3.0.0-rc13" in written_files[Path("terraform/template/ecs.tf")]
    assert "2.0.0-beta1" in written_files[Path("terraform/template/lambda.tf")]
    assert "0.5.0" in written_files[Path("terraform/template/main.tf")]


class TestServiceEnvironmentDetection:
    """Tests for detecting presence of service environment folder"""

    def test_has_service_environment_returns_true_when_service_folder_exists(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """Service folder exists at terraform/service/"""
        file_handler.folder_exists.side_effect = lambda path: path == Path(
            "terraform/service/"
        )

        result = application.has_service_environment()

        assert result is True

    def test_has_service_environment_returns_false_when_service_folder_missing(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """Service folder does not exist - only test and prod"""
        file_handler.folder_exists.return_value = False

        result = application.has_service_environment()

        assert result is False

    def test_has_service_environment_checks_alternative_locations(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """Service folder exists at environments/service/"""
        file_handler.folder_exists.side_effect = lambda path: path == Path(
            "environments/service/"
        )

        result = application.has_service_environment()

        assert result is True


    def test_deployment_workflow_omits_skip_flag_when_service_folder_exists(
        self,
        application: DeploymentMigration,
        github_actions_author: GithubActionsAuthor,
        file_handler: FileHandler,
    ) -> None:
        """Generated workflow should NOT include skip flag when service exists"""
        # Service folder exists
        file_handler.folder_exists.side_effect = lambda path: path == Path(
            "terraform/service/"
        )
        # Mock openapi spec detection to raise FileNotFoundError (no .circleci folder)
        file_handler.read_file.side_effect = FileNotFoundError()

        github_actions_author.create_deployment_workflow.return_value = (
            "name: Deploy\njobs:\n  terraform-changes:\n    uses: ...\n"
        )
        github_actions_author.create_pull_request_workflow.return_value = (
            "name: PR\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
        )

        application.create_github_action_deployment_workflow(
            repository_name="my-repo",
            application_name="my-app",
            application_build_tool=ApplicationBuildTool.PYTHON,
            application_runtime_target=ApplicationRuntimeTarget.ECS,
            terraform_base_folder=Path("terraform"),
        )

        # Verify the workflow generator was called without skip flag (or False)
        github_actions_author.create_deployment_workflow.assert_called_once()
        call_kwargs = github_actions_author.create_deployment_workflow.call_args.kwargs
        skip_flag = call_kwargs.get("skip_service_environment", False)
        assert skip_flag is False

    def test_pull_request_workflow_includes_skip_flag_when_no_service_folder(
        self,
        application: DeploymentMigration,
        github_actions_author: GithubActionsAuthor,
        file_handler: FileHandler,
    ) -> None:
        """PR workflow should also get the skip flag"""
        # No service folder exists
        file_handler.folder_exists.return_value = False
        # Mock openapi spec detection to raise FileNotFoundError (no .circleci folder)
        file_handler.read_file.side_effect = FileNotFoundError()

        github_actions_author.create_pull_request_workflow.return_value = (
            "name: PR\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
        )
        github_actions_author.create_deployment_workflow.return_value = (
            "name: Deploy\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n"
        )

        application.create_github_action_deployment_workflow(
            repository_name="my-repo",
            application_name="my-app",
            application_build_tool=ApplicationBuildTool.PYTHON,
            application_runtime_target=ApplicationRuntimeTarget.ECS,
            terraform_base_folder=Path("terraform"),
        )

        # Verify PR workflow generator was called with skip flag
        github_actions_author.create_pull_request_workflow.assert_called_once()
        call_kwargs = (
            github_actions_author.create_pull_request_workflow.call_args.kwargs
        )
        assert call_kwargs.get("skip_service_environment") is True


class TestTeamSpecificAWSRole:
    """Tests for team-specific AWS role detection and configuration"""

    def test_requires_custom_aws_role_for_alternativ_transport_team(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """alternativ-transport team requires custom AWS role"""
        file_handler.current_folder_name.return_value = (
            "alternativ-transport-brudd-backend"
        )

        result = application.requires_custom_aws_role()

        assert result is True

    def test_requires_custom_aws_role_for_drifts_informasjon_team(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """drifts-informasjon team requires custom AWS role"""
        file_handler.current_folder_name.return_value = "drifts-informasjon-api"

        result = application.requires_custom_aws_role()

        assert result is True

    def test_requires_custom_aws_role_for_trafficcontrol_team(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """trafficcontrol team requires custom AWS role"""
        file_handler.current_folder_name.return_value = "trafficcontrol-service"

        result = application.requires_custom_aws_role()

        assert result is True

    def test_requires_custom_aws_role_returns_false_for_standard_team(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """Standard teams do not require custom AWS role"""
        file_handler.current_folder_name.return_value = "booking-api"

        result = application.requires_custom_aws_role()

        assert result is False

    def test_get_aws_role_name_returns_custom_role_for_special_teams(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """Returns github_actions_assume_role for teams needing custom role"""
        file_handler.current_folder_name.return_value = (
            "alternativ-transport-brudd-backend"
        )

        result = application.get_aws_role_name()

        assert result == "github_actions_assume_role"

    def test_get_aws_role_name_returns_none_for_standard_teams(
        self,
        application: DeploymentMigration,
        file_handler: FileHandler,
    ) -> None:
        """Returns None for standard teams using default role"""
        file_handler.current_folder_name.return_value = "booking-api"

        result = application.get_aws_role_name()

        assert result is None


class TestWorkflowGenerationWithCustomAWSRole:
    """Tests for AWS role parameter in workflow generation"""

    def test_deployment_workflow_includes_aws_role_for_special_teams(
        self,
        application: DeploymentMigration,
        github_actions_author: GithubActionsAuthor,
        file_handler: FileHandler,
    ) -> None:
        """Workflow should include aws-role-name-to-assume for special teams"""
        file_handler.current_folder_name.return_value = (
            "alternativ-transport-brudd-backend"
        )
        file_handler.folder_exists.return_value = True
        file_handler.read_file.side_effect = FileNotFoundError()

        github_actions_author.create_deployment_workflow.return_value = "name: Deploy\n"
        github_actions_author.create_pull_request_workflow.return_value = "name: PR\n"

        application.create_github_action_deployment_workflow(
            repository_name="alternativ-transport-brudd-backend",
            application_name="brudd-backend",
            application_build_tool=ApplicationBuildTool.PYTHON,
            application_runtime_target=ApplicationRuntimeTarget.ECS,
            terraform_base_folder=Path("terraform"),
        )

        # Verify the workflow generator was called with aws_role_name
        github_actions_author.create_deployment_workflow.assert_called_once()
        call_kwargs = github_actions_author.create_deployment_workflow.call_args.kwargs
        assert call_kwargs.get("aws_role_name") == "github_actions_assume_role"

    def test_deployment_workflow_omits_aws_role_for_standard_teams(
        self,
        application: DeploymentMigration,
        github_actions_author: GithubActionsAuthor,
        file_handler: FileHandler,
    ) -> None:
        """Workflow should NOT include aws-role-name-to-assume for standard teams"""
        file_handler.current_folder_name.return_value = "booking-api"
        file_handler.folder_exists.return_value = True
        file_handler.read_file.side_effect = FileNotFoundError()

        github_actions_author.create_deployment_workflow.return_value = "name: Deploy\n"
        github_actions_author.create_pull_request_workflow.return_value = "name: PR\n"

        application.create_github_action_deployment_workflow(
            repository_name="booking-api",
            application_name="booking",
            application_build_tool=ApplicationBuildTool.PYTHON,
            application_runtime_target=ApplicationRuntimeTarget.ECS,
            terraform_base_folder=Path("terraform"),
        )

        # Verify the workflow generator was called with None or no aws_role_name
        github_actions_author.create_deployment_workflow.assert_called_once()
        call_kwargs = github_actions_author.create_deployment_workflow.call_args.kwargs
        assert call_kwargs.get("aws_role_name") is None

    def test_pull_request_workflow_includes_aws_role_for_special_teams(
        self,
        application: DeploymentMigration,
        github_actions_author: GithubActionsAuthor,
        file_handler: FileHandler,
    ) -> None:
        """PR workflow should also get AWS role parameter for special teams"""
        file_handler.current_folder_name.return_value = "drifts-informasjon-api"
        file_handler.folder_exists.return_value = True
        file_handler.read_file.side_effect = FileNotFoundError()

        github_actions_author.create_deployment_workflow.return_value = "name: Deploy\n"
        github_actions_author.create_pull_request_workflow.return_value = "name: PR\n"

        application.create_github_action_deployment_workflow(
            repository_name="drifts-informasjon-api",
            application_name="drifts-api",
            application_build_tool=ApplicationBuildTool.PYTHON,
            application_runtime_target=ApplicationRuntimeTarget.ECS,
            terraform_base_folder=Path("terraform"),
        )

        # Verify PR workflow generator was called with aws_role_name
        github_actions_author.create_pull_request_workflow.assert_called_once()
        call_kwargs = (
            github_actions_author.create_pull_request_workflow.call_args.kwargs
        )
        assert call_kwargs.get("aws_role_name") == "github_actions_assume_role"


def test_generate_pr_workflows_creates_only_pr_files(
    application: DeploymentMigration,
    file_handler: FileHandler,
    github_actions_author: GithubActionsAuthor,
) -> None:
    """PR workflow generation should create only 2 files, not 3."""
    created_files = {}
    file_handler.create_file.side_effect = lambda path, content: (
        created_files.update({path: content})
    )
    file_handler.read_file.side_effect = FileNotFoundError()  # No .circleci

    github_actions_author.create_pull_request_workflow.return_value = "pr workflow"
    github_actions_author.create_pull_request_comment_workflow.return_value = (
        "pr comment workflow"
    )

    application.generate_pr_workflows(
        repository_name="test-app",
        application_name="test-app",
        application_build_tool=ApplicationBuildTool.PYTHON,
        application_runtime_target=ApplicationRuntimeTarget.ECS,
        terraform_base_folder=Path("terraform"),
    )

    # Only PR workflows created
    assert Path(".github/workflows/pull-request.yml") in created_files
    assert Path(".github/workflows/pull-request-comment.yml") in created_files
    assert Path(".github/workflows/build-and-deploy.yml") not in created_files

    # Deployment workflow method not called
    github_actions_author.create_deployment_workflow.assert_not_called()


def test_generate_deployment_workflow_creates_only_deployment_file(
    application: DeploymentMigration,
    file_handler: FileHandler,
    github_actions_author: GithubActionsAuthor,
) -> None:
    """Deployment workflow generation should create only 1 file."""
    created_files = {}
    file_handler.create_file.side_effect = lambda path, content: (
        created_files.update({path: content})
    )
    file_handler.read_file.side_effect = FileNotFoundError()  # No .circleci

    github_actions_author.create_deployment_workflow.return_value = (
        "deployment workflow"
    )

    application.generate_deployment_workflow(
        repository_name="test-app",
        application_name="test-app",
        application_build_tool=ApplicationBuildTool.PYTHON,
        application_runtime_target=ApplicationRuntimeTarget.ECS,
        terraform_base_folder=Path("terraform"),
    )

    # Only deployment workflow created
    assert Path(".github/workflows/build-and-deploy.yml") in created_files
    assert Path(".github/workflows/pull-request.yml") not in created_files
    assert Path(".github/workflows/pull-request-comment.yml") not in created_files

    # PR workflow methods not called
    github_actions_author.create_pull_request_workflow.assert_not_called()
    github_actions_author.create_pull_request_comment_workflow.assert_not_called()


def test_ensure_cache_in_gitignore_creates_gitignore_if_not_exists(
    application: DeploymentMigration, file_handler: FileHandler
):
    """Test that .gitignore is created with cache entry if it doesn't exist."""
    file_handler.file_exists.return_value = False

    application.ensure_cache_in_gitignore()

    file_handler.create_file.assert_called_once_with(
        Path(".gitignore"), ".vydev-cli-cache.json\n"
    )


def test_ensure_cache_in_gitignore_adds_entry_to_existing_gitignore(
    application: DeploymentMigration, file_handler: FileHandler
):
    """Test that cache entry is added to existing .gitignore if not present."""
    existing_content = "*.pyc\n__pycache__/\n"
    file_handler.file_exists.return_value = True
    file_handler.read_file.return_value = existing_content

    application.ensure_cache_in_gitignore()

    expected_content = existing_content + ".vydev-cli-cache.json\n"
    file_handler.overwrite_file.assert_called_once_with(
        Path(".gitignore"), expected_content
    )


def test_ensure_cache_in_gitignore_does_not_duplicate_entry(
    application: DeploymentMigration, file_handler: FileHandler
):
    """Test that it doesn't duplicate the entry if already present."""
    existing_content = "*.pyc\n.vydev-cli-cache.json\n__pycache__/\n"
    file_handler.file_exists.return_value = True
    file_handler.read_file.return_value = existing_content

    application.ensure_cache_in_gitignore()

    # Should not modify the file
    file_handler.overwrite_file.assert_not_called()
    file_handler.create_file.assert_not_called()


def test_ensure_cache_in_gitignore_handles_missing_trailing_newline(
    application: DeploymentMigration, file_handler: FileHandler
):
    """Test that it handles .gitignore files without trailing newline."""
    existing_content = "*.pyc\n__pycache__/"  # No trailing newline
    file_handler.file_exists.return_value = True
    file_handler.read_file.return_value = existing_content

    application.ensure_cache_in_gitignore()

    expected_content = "*.pyc\n__pycache__/\n.vydev-cli-cache.json\n"
    file_handler.overwrite_file.assert_called_once_with(
        Path(".gitignore"), expected_content
    )


class TestSpringBootModuleRC3Upgrade:
    """Tests for Spring Boot module upgrade to version 3.0.0-rc3."""

    def test_spring_boot_module_version_updated_to_rc3(
        self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        file_handler: FileHandler,
    ):
        """Test that Spring Boot module version is updated from rc1 to rc3."""
        spring_boot_module = (
            "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service"
        )
        found_module = {
            "github.com/nsbno/terraform-aws-ecs-service": None,
            "github.com/nsbno/terraform-aws-lambda": None,
            spring_boot_module: {
                "name": "spring_boot_service",
                "file_path": Path("terraform/main.tf"),
            },
            "github.com/nsbno/terraform-aws-account-metadata": None,
        }

        terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
            found_module.get(module)
        )
        terraform_modifier.has_module.return_value = False  # No ECS module

        terraform_config = (
            'module "spring_boot_service" {\n'
            '  source  = "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service"\n'
            '  version = "3.0.0-rc1"\n'
            "}\n"
        )
        file_handler.read_file.return_value = terraform_config

        # Mock update_module_versions to return updated config
        terraform_modifier.update_module_versions.return_value = (
            terraform_config.replace("3.0.0-rc1", "3.0.0-rc3")
        )

        application.upgrade_terraform_application_resources(
            terraform_infrastructure_folder="terraform"
        )

        # Verify update_module_versions was called with rc3
        update_calls = [
            call
            for call in terraform_modifier.mock_calls
            if call[0] == "update_module_versions"
        ]

        # Find the call that updated Spring Boot module
        spring_boot_updated = False
        for call in update_calls:
            if (
                "target_modules" in call.kwargs
                and spring_boot_module in call.kwargs["target_modules"]
            ):
                assert call.kwargs["target_modules"][spring_boot_module] == "3.0.0-rc3"
                spring_boot_updated = True

        assert (
            spring_boot_updated
        ), "Spring Boot module should be updated to version 3.0.0-rc3"

    def test_spring_boot_module_docker_image_variable_removed(
        self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        file_handler: FileHandler,
    ):
        """Test that docker_image variable is removed from Spring Boot modules."""
        spring_boot_module = (
            "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service"
        )
        found_module = {
            "github.com/nsbno/terraform-aws-ecs-service": None,
            "github.com/nsbno/terraform-aws-lambda": None,
            spring_boot_module: {
                "name": "spring_boot_service",
                "file_path": Path("terraform/main.tf"),
            },
            "github.com/nsbno/terraform-aws-account-metadata": None,
        }

        terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
            found_module.get(module)
        )
        # has_module returns True only for Spring Boot module
        terraform_modifier.has_module.side_effect = (
            lambda module, *_: module == spring_boot_module
        )

        terraform_config = (
            'module "spring_boot_service" {\n'
            '  source  = "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service"\n'
            '  version = "3.0.0-rc3"\n'
            "\n"
            "  docker_image = local.docker_image\n"
            '  service_name = "my-service"\n'
            "}\n"
        )
        file_handler.read_file.return_value = terraform_config

        application.upgrade_terraform_application_resources(
            terraform_infrastructure_folder="terraform"
        )

        # Verify update_spring_boot_service_module was called
        terraform_modifier.update_spring_boot_service_module.assert_called_once()

    def test_spring_boot_module_datadog_tags_block_removed(
        self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        file_handler: FileHandler,
    ):
        """Test that datadog_tags block is removed from Spring Boot modules."""
        spring_boot_module = (
            "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service"
        )
        found_module = {
            "github.com/nsbno/terraform-aws-ecs-service": None,
            "github.com/nsbno/terraform-aws-lambda": None,
            spring_boot_module: {
                "name": "spring_boot_service",
                "file_path": Path("terraform/main.tf"),
            },
            "github.com/nsbno/terraform-aws-account-metadata": None,
        }

        terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
            found_module.get(module)
        )
        # has_module returns True only for Spring Boot module
        terraform_modifier.has_module.side_effect = (
            lambda module, *_: module == spring_boot_module
        )

        terraform_config = (
            'module "spring_boot_service" {\n'
            '  source  = "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service"\n'
            '  version = "3.0.0-rc3"\n'
            "\n"
            "  datadog_tags = {\n"
            "    environment = var.environment\n"
            "    version     = local.image_tag\n"
            "  }\n"
            '  service_name = "my-service"\n'
            "}\n"
        )
        file_handler.read_file.return_value = terraform_config

        application.upgrade_terraform_application_resources(
            terraform_infrastructure_folder="terraform"
        )

        # Verify update_spring_boot_service_module was called
        terraform_modifier.update_spring_boot_service_module.assert_called_once()

    def test_spring_boot_module_repository_url_added(
        self,
        application: DeploymentMigration,
        terraform_modifier: Terraform,
        file_handler: FileHandler,
    ):
        """Test that repository_url variable is added to Spring Boot modules."""
        spring_boot_module = (
            "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service"
        )
        found_module = {
            "github.com/nsbno/terraform-aws-ecs-service": None,
            "github.com/nsbno/terraform-aws-lambda": None,
            spring_boot_module: {
                "name": "spring_boot_service",
                "file_path": Path("terraform/main.tf"),
            },
            "github.com/nsbno/terraform-aws-account-metadata": None,
        }

        terraform_modifier.find_module.side_effect = lambda module, *_, **__: (
            found_module.get(module)
        )
        # has_module returns True only for Spring Boot module
        terraform_modifier.has_module.side_effect = (
            lambda module, *_: module == spring_boot_module
        )

        terraform_config = (
            'module "spring_boot_service" {\n'
            '  source  = "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service"\n'
            '  version = "3.0.0-rc3"\n'
            "\n"
            '  service_name = "my-service"\n'
            "}\n"
        )
        file_handler.read_file.return_value = terraform_config

        application.upgrade_terraform_application_resources(
            terraform_infrastructure_folder="terraform"
        )

        # Verify update_spring_boot_service_module was called
        terraform_modifier.update_spring_boot_service_module.assert_called_once()
