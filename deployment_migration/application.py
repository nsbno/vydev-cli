import abc
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self, Any, Optional


class ApplicationBuildTool(StrEnum):
    PYTHON = "python"
    GRADLE = "gradle"


class ApplicationRuntimeTarget(StrEnum):
    LAMBDA = "lambda"
    ECS = "ecs"


class FileHandler(abc.ABC):
    @abc.abstractmethod
    def create_file(self: Self, path: Path, content: str) -> None:
        pass

    @abc.abstractmethod
    def read_file(self: Self, path: Path) -> str:
        pass

    @abc.abstractmethod
    def overwrite_file(self: Self, path: Path, content: str) -> None:
        pass

    @abc.abstractmethod
    def folder_exists(self: Self, path: Path):
        pass


class VersionControl(abc.ABC):
    @abc.abstractmethod
    def commit(self: Self, message: str):
        pass


class TerraformModifyer(abc.ABC):
    @abc.abstractmethod
    def modify_terraform_file(
        self: Self,
        terraform_config: str,
        replacements: dict,
    ) -> str:
        pass

    def update_module_versions(
        self: Self,
        terraform_config: str,
        target_modules: dict[str, str],
    ) -> str:
        pass

    def add_module(
        self: Self,
        terraform_config: str,
        name: str,
        source: str,
        version: str,
        variables: Optional[dict[str, Any]] = None,
    ) -> str:
        pass


class ParameterStore(abc.ABC):
    @abc.abstractmethod
    def create_parameter(self: Self, name: str, value: str):
        pass


class GithubActionsAuthor(abc.ABC):
    def create_deployment_workflow(
        self: Self,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: Path,
    ) -> str:
        pass


@dataclass
class DeploymentMigration:
    """Migrate from the old to the new deployment pipeline"""

    version_control: VersionControl
    file_handler: FileHandler
    github_actions_author: GithubActionsAuthor
    terraform_modifier: TerraformModifyer
    parameter_store: ParameterStore

    def _find_folder(self: Self, potential_folders: list[Path]) -> Path | None:
        """Finds a folder in the current working directory"""
        return next(
            (
                path
                for path in potential_folders
                if self.file_handler.folder_exists(path)
            ),
            None,
        )

    def find_terraform_infrastructure_folder(self: Self) -> Path:
        """Finds the terraform infrastructure or template folder"""
        potential_folder_locations = [
            Path("terraform/template/"),
            Path("terraform/modules/template/"),
            Path("infrastructure/"),
        ]

        folder = self._find_folder(potential_folder_locations)

        if folder is None:
            raise FileNotFoundError("Could not find a terraform infrastructure folder")

        return folder

    def find_terraform_environment_folder(self: Self, environment: str) -> Path:
        """Finds the folder for a terraform environment"""
        potential_folder_locations = [
            Path(f"terraform/environment/{environment}/"),
            Path(f"environments/{environment}/"),
        ]

        folder = self._find_folder(potential_folder_locations)

        if folder is None:
            raise FileNotFoundError("Could not find a terraform environment folder")

        return folder

    def create_github_action_deployment_workflow(
        self: Self,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: Path,
    ) -> None:
        """Creates the github action deployment workflow"""
        github_actions_deployment_workflow = (
            self.github_actions_author.create_deployment_workflow(
                application_name,
                application_build_tool,
                application_runtime_target,
                terraform_base_folder,
            )
        )

        self.file_handler.create_file(
            Path(".github/workflows/deploy.yml"), github_actions_deployment_workflow
        )

    def upgrade_aws_repo_terraform_resources(
        self: Self,
        terraform_folder: str,
    ):
        """Adds required resources to the AWS repo"""
        file_to_modify = Path(f"{terraform_folder}/main.tf")

        terraform_config = self.file_handler.read_file(file_to_modify)

        updated_config = self.terraform_modifier.add_module(
            terraform_config,
            name="github_actions_oidc",
            source="",  # TODO: Module URL
            version="",  # TODO
        )

        self.file_handler.overwrite_file(file_to_modify, updated_config)

    def create_parameter_store_version_parameter(
        self: Self, application_name: str, temporary_version: str = "latest"
    ) -> None:
        """Creates the parameter store version parameter for the application"""
        parameter_name = f"/__platform__/versions/{application_name}"

        self.parameter_store.create_parameter(parameter_name, temporary_version)

    def upgrade_terraform_application_resources(
        self: Self,
        terraform_infrastructure_folder: str,
    ) -> None:
        """Upgrades the ECS and Lambda modules"""
        terraform_main_file_path = Path(f"{terraform_infrastructure_folder}/main.tf")
        terraform_config = self.file_handler.read_file(terraform_main_file_path)

        updated_config = self.terraform_modifier.update_module_versions(
            terraform_config,
            target_modules={
                "https://github.com/nsbno/terraform-aws-ecs-service": "6.0.0-beta1",
                "https://github.com/nsbno/terraform-aws-lambda": "6.0.0-beta1",
            },
        )

        self.file_handler.overwrite_file(terraform_main_file_path, updated_config)
