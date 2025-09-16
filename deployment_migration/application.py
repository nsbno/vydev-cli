import abc
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self, Any, Optional

import yaml


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
    def folder_exists(self: Self, path: Path) -> Path | None:
        pass

    @abc.abstractmethod
    def get_subfolders(self: Self, path: Path) -> list[Path]:
        pass

    @abc.abstractmethod
    def delete_folder(self: Self, folder: Path, not_found_ok: bool) -> None:
        pass

    @abc.abstractmethod
    def current_folder_name(self) -> str:
        pass

    @abc.abstractmethod
    def file_exists(self, location: str) -> bool:
        pass


class VersionControl(abc.ABC):
    @abc.abstractmethod
    def commit(self: Self, message: str) -> None:
        pass

    @abc.abstractmethod
    def get_origin(self: Self) -> str:
        pass

    @abc.abstractmethod
    def push(self: Self) -> None:
        pass

    @abc.abstractmethod
    def changed_files(self) -> list[str]:
        pass


class Terraform(abc.ABC):
    @abc.abstractmethod
    def find_provider(
        self: Self, provider_name: str, terraform_folder: Path
    ) -> dict[str, Any]:
        """Finds a provider in the terraform config"""
        pass

    @abc.abstractmethod
    def update_provider_versions(
        self: Self,
        terraform_config: str,
        target_providers: dict[str, str],
    ) -> str:
        pass

    @abc.abstractmethod
    def remove_vydev_artifact_reference(
        self: Self,
        terraform_config: str,
    ) -> str:
        pass

    @abc.abstractmethod
    def add_data_source(
        self: Self,
        terraform_config: str,
        resource: str,
        name: str,
        variables: dict[str, str],
    ) -> str:
        pass

    @abc.abstractmethod
    def update_module_versions(
        self: Self,
        terraform_config: str,
        target_modules: dict[str, str],
    ) -> str:
        pass

    @abc.abstractmethod
    def add_module(
        self: Self,
        terraform_config: str,
        name: str,
        source: str,
        version: str,
        variables: Optional[dict[str, Any]] = None,
    ) -> str:
        pass

    @abc.abstractmethod
    def has_module(self: Self, module_source: str, infrastructure_folder: Path) -> bool:
        pass

    @abc.abstractmethod
    def find_module(
        self: Self, module_source: str, infrastructure_folder: Path
    ) -> Optional[dict[str, Any]]:
        """Finds a module in the terraform config"""
        pass

    @abc.abstractmethod
    def add_variable(
        self: Self, terraform_config: str, target_module: str, variables: dict[str, Any]
    ) -> str:
        pass

    @abc.abstractmethod
    def add_test_listener_to_ecs_module(
        self: Self, terraform_config: str, metadata_module_name: str
    ) -> str:
        """Add test_listener variable to the ECS module in a Terraform configuration.

        This is a specific implementation for handling the test listener case.
        """
        pass

    @abc.abstractmethod
    def find_account_id(self: Self, folder: str) -> str:
        """Finds the AWS account ID in the terraform folder

        This is used for the environment folders, to figure out which account to use.
        """
        pass

    @abc.abstractmethod
    def get_parameter(
        self, type_: str, parameter: str, module_folder: Path
    ) -> list[str]:
        """Finds the value of a given datasource in the terraform folder"""
        pass

    @abc.abstractmethod
    def replace_image_tag_on_ecs_module(
        self: Self,
        terraform_config: str,
        ecr_repository_data_source_name: str,
    ) -> str:
        pass


class AWS(abc.ABC):
    @abc.abstractmethod
    def create_parameter(self: Self, name: str, value: str, profile_name: str = ""):
        pass

    @abc.abstractmethod
    def find_aws_profile_names(self: Self, account_id: str) -> list[str]:
        """Finds the AWS profile name(s) for the account ID"""
        pass


class GithubActionsAuthor(abc.ABC):
    @abc.abstractmethod
    def create_deployment_workflow(
        self: Self,
        repository_name: str,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: Path,
        dockerfile_path: str = None,
        gradle_file_path: str = None,
        openapi_spec_path: str = None,
    ) -> str:
        pass

    @abc.abstractmethod
    def create_pull_request_workflow(
        self: Self,
        repository_name: str,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: Path,
        dockerfile_path: str = None,
    ) -> str:
        pass


class ApplicationContext(abc.ABC):
    @abc.abstractmethod
    def find_build_tool(self: Self) -> ApplicationBuildTool:
        """Finds the build tool used for the application"""
        pass

    @abc.abstractmethod
    def find_application_artifact_name(self: Self) -> list[str]:
        """Finds the name of the application"""
        pass


class GithubApi(abc.ABC):
    @abc.abstractmethod
    def ensure_authenticated(self: Self) -> None:
        """Checks if the user is authenticated with GitHub CLI"""
        pass

    @abc.abstractmethod
    def create_environment(self: Self, repo: str, environment: str) -> None:
        """Creates a GitHub environment"""
        pass

    @abc.abstractmethod
    def add_variable_to_environment(
        self: Self, repo: str, environment: str, name: str, value: str
    ) -> None:
        """Adds a variable to a GitHub environment"""
        pass


class NotFoundError(Exception):
    pass


@dataclass
class DeploymentMigration:
    """Migrate from the old to the new deployment pipeline"""

    version_control: VersionControl
    file_handler: FileHandler
    github_actions_author: GithubActionsAuthor
    github_api: GithubApi
    terraform: Terraform
    aws: AWS
    application_context: ApplicationContext

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
            Path("modules/environment_account_setup"),
        ]

        folder = self._find_folder(potential_folder_locations)

        if folder is None:
            raise FileNotFoundError("Could not find a terraform infrastructure folder")

        return folder

    def find_terraform_environment_folder(self: Self, environment: str) -> Path:
        """Finds the folder for a terraform environment"""
        potential_folder_locations = [
            Path(f"terraform/{environment}/"),
            Path(f"terraform/environment/{environment}/"),
            Path(f"environments/{environment}/"),
        ]

        folder = self._find_folder(potential_folder_locations)

        if folder is None:
            raise FileNotFoundError("Could not find a terraform environment folder")

        return folder

    def find_all_environment_folders(self: Self) -> list[Path]:
        """Finds all terraform environment folders"""
        potential_folder_locations = [
            Path("terraform/"),
            Path("environments/"),
        ]

        folders = [
            Path(folder)
            for parent in potential_folder_locations
            if parent.exists()
            for folder in self.file_handler.get_subfolders(parent)
        ]

        folders_to_find = [
            "service",
            "dev",
            "development",
            "test",
            "testing",
            "stage",
            "staging",
            "prod",
            "production",
        ]

        stripped_folders = [
            folder for folder in folders if folder.name.lower() in folders_to_find
        ]

        return stripped_folders

    def _find_openapi_spec(self) -> Path | None:
        circle_ci_config_file = self.file_handler.read_file(
            Path(".circleci/config.yml")
        )
        circle_ci_config = yaml.safe_load(circle_ci_config_file)

        try:
            push_api_spec_job = next(
                job
                for workflow in circle_ci_config["workflows"].values()
                for job in workflow["jobs"]
                if "documentation/push-api-spec" in job
            )
        except StopIteration:
            return None

        path = push_api_spec_job["documentation/push-api-spec"]["openapi-path"]
        return Path(path)

    def create_github_action_deployment_workflow(
        self: Self,
        repository_name: str,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: Path,
    ) -> None:
        """Creates the github action deployment workflow"""
        # Find Dockerfile if we're using ECS
        dockerfile_path = None
        if application_runtime_target == ApplicationRuntimeTarget.ECS:
            try:
                dockerfile_path = str(self.find_dockerfile())
            except NotFoundError:
                # If Dockerfile is not found, we'll proceed without it
                pass

        # Find Gradle folder if we're using Gradle
        if application_build_tool == ApplicationBuildTool.GRADLE:
            try:
                gradle_folder_path = str(self.find_gradle_folder())
            except NotFoundError:
                # If Gradle folder is not found, we'll proceed without it
                gradle_folder_path = None

        # TODO: Find OpenAPI Spec if we have a OpenAPI Spec
        try:
            openapi_spec_path = str(self._find_openapi_spec())
        except NotFoundError:
            openapi_spec_path = None

        github_actions_deployment_workflow = (
            self.github_actions_author.create_deployment_workflow(
                repository_name,
                application_name,
                application_build_tool,
                application_runtime_target,
                terraform_base_folder,
                dockerfile_path=dockerfile_path,
                openapi_spec_path=str(openapi_spec_path),
            )
        )

        self.file_handler.create_file(
            Path(".github/workflows/deploy.yml"), github_actions_deployment_workflow
        )

        pull_request_workflow = self.github_actions_author.create_pull_request_workflow(
            repository_name,
            application_name,
            application_build_tool,
            application_runtime_target,
            terraform_base_folder,
            dockerfile_path=dockerfile_path,
        )

        self.file_handler.create_file(
            Path(".github/workflows/pull-request.yml"), pull_request_workflow
        )

    def upgrade_aws_repo_terraform_resources(
        self: Self,
        terraform_folder: str,
    ):
        """Adds required resources to the AWS repo"""
        file_to_modify = Path(f"{terraform_folder}/main.tf")

        terraform_config = self.file_handler.read_file(file_to_modify)

        environment_variable = (
            "service" if "service" in terraform_folder else "var.environment"
        )

        if self.terraform.has_module(
            "github.com/nsbno/terraform-aws-github-oidc", Path(terraform_folder)
        ):
            updated_config = self.terraform.update_module_versions(
                terraform_config,
                target_modules={
                    "github.com/nsbno/terraform-aws-github-oidc": "0.1.0",
                },
            )
        else:
            updated_config = self.terraform.add_module(
                terraform_config,
                name="github_actions_oidc",
                source="github.com/nsbno/terraform-aws-github-oidc",
                version="0.1.0",
                variables={"environment": environment_variable},
            )

        self.file_handler.overwrite_file(file_to_modify, updated_config)

    def upgrade_aws_repo_alb_resources(
        self: Self,
        infrastructure_folder: Path,
    ):
        """Updates or adds ALB to the AWS repo"""
        loadbalancer_module = self.terraform.find_module(
            "github.com/nsbno/terraform-aws-loadbalancer",
            infrastructure_folder,
        )

        terraform_config = self.file_handler.read_file(loadbalancer_module["file_path"])

        if not loadbalancer_module:
            raise NotFoundError(
                "You are not using the shared loadbalancer module.\n"
                "Please migrate to using the following module manually https://github.com/nsbno/terraform-aws-loadbalancer"
            )

        updated_config = self.terraform.update_module_versions(
            terraform_config,
            target_modules={"github.com/nsbno/terraform-aws-loadbalancer": "5.1.0"},
        )

        self.file_handler.overwrite_file(
            loadbalancer_module["file_path"], updated_config
        )

    def find_environment_aws_profile_names(self) -> dict[str, str]:
        runtime_environments = {}

        # TODO: Removed this for MVP testing with users, add it back!!!
        #      runtime_environments_to_check = ["stage", "dev", "prod", "test"]
        runtime_environments_to_check = ["test"]
        for environment in runtime_environments_to_check:
            try:
                runtime_environments[environment] = (
                    self.find_terraform_environment_folder(environment)
                )
            except FileNotFoundError:
                pass

        account_ids = {}
        for environment, folder in runtime_environments.items():
            account_ids[environment] = self.terraform.find_account_id(folder)

        profile_names = {}
        for environment, account_id in account_ids.items():
            names = self.aws.find_aws_profile_names(account_id)
            if len(names) == 0:
                raise NotFoundError(
                    f"Could not find an AWS profile name for account {account_id}"
                )
            elif len(names) == 1:
                name = names[0]
            else:
                name = next(
                    (name for name in names if "AdministratorAccess" in name), names[0]
                )

            profile_names[environment] = name

        return profile_names

    def upgrade_application_repo_terraform_provider_versions(
        self: Self,
        folders: list[str],
    ):
        """Updates the provider versions in the AWS repo

        :param folders: All folders with Terraform Config
        """
        for folder in folders:
            provider_data = self.terraform.find_provider("aws", Path(folder))
            if not provider_data:
                continue

            config = self.file_handler.read_file(provider_data["file"])
            config = self.terraform.update_provider_versions(
                config,
                target_providers={
                    "aws": "~> 6.4.0",
                },
            )
            self.file_handler.overwrite_file(provider_data["file"], config)

    def replace_image_with_ecr_repository_url(
        self: Self,
        terraform_infrastructure_folder: str,
        repository_name: str,
        service_account_id: str,
    ):
        terraform_main_file_path = Path(f"{terraform_infrastructure_folder}/main.tf")
        terraform_config = self.file_handler.read_file(terraform_main_file_path)

        terraform_config = self.terraform.add_data_source(
            terraform_config,
            "aws_ecr_repository",
            name="this",
            variables={
                "name": repository_name,
                "registry_id": service_account_id,
            },
        )

        # terraform_config = self.terraform.remove_vydev_artifact_reference(
        #     terraform_config
        # )

        terraform_config = self.terraform.replace_image_tag_on_ecs_module(
            terraform_config, "this"
        )

        self.file_handler.overwrite_file(terraform_main_file_path, terraform_config)

    def upgrade_terraform_application_resources(
        self: Self,
        terraform_infrastructure_folder: str,
    ) -> None:
        """Upgrades the ECS and Lambda modules"""
        terraform_main_file_path = Path(f"{terraform_infrastructure_folder}/main.tf")
        terraform_config = self.file_handler.read_file(terraform_main_file_path)

        terraform_config = self.terraform.update_module_versions(
            terraform_config,
            target_modules={
                "github.com/nsbno/terraform-aws-ecs-service": "3.0.0-rc3",
                # TODO: This is not released yet
                "github.com/nsbno/terraform-aws-lambda": "2.0.0-beta1",
                "github.com/nsbno/terraform-digitalekanaler-modules//spring-boot-service": "utviklerplattform",
                "github.com/nsbno/terraform-aws-account-metadata": "0.5.0",
            },
        )

        if self.terraform.has_module(
            "github.com/nsbno/terraform-aws-ecs-service",
            Path(terraform_infrastructure_folder),
        ):
            module_info = self.terraform.find_module(
                "github.com/nsbno/terraform-aws-account-metadata",
                Path(terraform_infrastructure_folder),
            )
            if not module_info:
                module_name = "account_metadata"
                terraform_config = self.terraform.add_module(
                    terraform_config,
                    name=module_name,
                    source="github.com/nsbno/terraform-aws-account-metadata",
                    version="0.5.0",
                )
            else:
                module_name = module_info["name"]

            # We need to add a new variable for the test listener
            terraform_config = self.terraform.add_test_listener_to_ecs_module(
                terraform_config,
                metadata_module_name=module_name,
            )

        self.file_handler.overwrite_file(terraform_main_file_path, terraform_config)

    def is_repo_in_clean_state(self) -> bool:
        """Checks if the Git repository is in a clean state

        This means that there are no uncommitted changes.
        """
        try:
            import subprocess

            # Run git status --porcelain to check for uncommitted changes
            # If the output is empty, the repository is in a clean state
            result = subprocess.run(
                ["git", "status", "-uno", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip() == ""
        except subprocess.CalledProcessError as e:
            # Handle git command errors
            raise RuntimeError(f"Git operation failed: {e}")

    def find_application_name(self, terraform_folder: Path) -> str:
        try:
            names = self.terraform.get_parameter(
                "aws_ecr_repository", "name", terraform_folder
            )
        except NotFoundError:
            names = self.application_context.find_application_artifact_name()

        if len(names) > 1:
            raise NotFoundError(
                "Found more than one application name. That is not implemented yet."
            )
        elif len(names) == 0:
            raise NotFoundError("Could not find an application name")
        return names[0]

    def find_build_tool(self) -> ApplicationBuildTool:
        """Figures out which build tool is used for the application"""
        try:
            return self.application_context.find_build_tool()
        except Exception:
            raise NotFoundError("Could not find a build tool")

    def find_aws_runtime(self, infrastructure_folder: Path) -> ApplicationRuntimeTarget:
        """Finds the AWS runtime target for the application

        :raises NotFoundError: If the AWS runtime target cannot be found
        :raises NotImplementedError: If the application uses both ECS and Lambda
        """
        has_ecs_module = self.terraform.has_module(
            "github.com/nsbno/terraform-aws-ecs-service", infrastructure_folder
        )
        has_lambda_module = self.terraform.has_module(
            "github.com/nsbno/terraform-aws-lambda", infrastructure_folder
        )

        if has_ecs_module and has_lambda_module:
            raise NotImplementedError(
                "This tool does not support projects that run both ECS and Lambda. Update manually."
            )
        elif has_ecs_module:
            return ApplicationRuntimeTarget.ECS
        elif has_lambda_module:
            return ApplicationRuntimeTarget.LAMBDA
        else:
            raise NotFoundError("Could not find an AWS runtime target")

    def help_with_github_environment_setup(
        self, environment_folders: list[Path]
    ) -> tuple[str, str, dict[str, str]]:
        """Gives help for GitHub environment setup

        Manual at the moment

        :return: Link to the environment setup page and account IDs
        """
        account_ids = {}

        for environment_folder in environment_folders:
            environment_folder_name = environment_folder.name
            if environment_folder_name == "prod":
                environment_folder_name = "production"
            environment_name = environment_folder_name.capitalize()

            account_ids[environment_name] = self.terraform.find_account_id(
                str(environment_folder)
            )

        repo_address = self.version_control.get_origin()
        new_env_url = f"https://{repo_address}/settings/environments/new"

        return new_env_url, repo_address, account_ids

    def remove_old_deployment_setup(self: Self) -> None:
        """Removes the old deployment setup"""
        folders_to_remove = [Path(".deployment"), Path(".circleci")]

        for folder in folders_to_remove:
            self.file_handler.delete_folder(folder, not_found_ok=True)

    def commit_and_push_changes(self: Self, message: str) -> None:
        self.version_control.commit(message)
        self.version_control.push()

    def changed_files(self) -> list[str]:
        return self.version_control.changed_files()

    def is_aws_repo(self) -> bool:
        """Checks if the current folder is an -aws repo"""
        cwd = self.file_handler.current_folder_name()

        return cwd.endswith("-aws")

    def find_gradle_folder(self: Self) -> Path:
        """Finds the gradle folder in the current folder"""
        # TODO: Go trough all top level folders and check if they are gradle projects
        #       If so, use that one instead of the one in the root folder
        gradle_folders = [
            folder
            for folder in self.file_handler.get_subfolders(Path("."))
            if self.file_handler.file_exists(str(folder / "gradlew"))
        ]

        if len(gradle_folders) == 0:
            raise NotFoundError("Could not find a gradle folder")
        elif len(gradle_folders) > 1:
            raise NotFoundError("Found more than one gradle folder")
        else:
            return gradle_folders[0]

    def find_dockerfile(self) -> Path:
        """Finds the Dockerfile in the current folder"""
        locations = ["Dockerfile", "Docker/Dockerfile", "docker/Dockerfile"]

        for location in locations:
            if self.file_handler.file_exists(location):
                return Path(location)

        raise NotFoundError("Could not find a Dockerfile")

    def initialize_github_environments(
        self, accounts: dict[str, str], repo_address: str
    ) -> None:
        # This will create the environment if it doesn't exist
        self.github_api.ensure_authenticated()
        repo = repo_address.split("github.com/")[-1]
        for environment, account_id in accounts.items():
            try:
                self.github_api.create_environment(repo=repo, environment=environment)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to create GitHub environment '{environment}': {e}"
                )

            try:
                self.github_api.add_variable_to_environment(
                    repo=repo,
                    environment=environment,
                    name="AWS_ACCOUNT_ID",
                    value=account_id,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to add AWS_ACCOUNT_ID variable to environment '{environment}': {e}"
                )
