"""Stub implementations for manual testing of the CLI."""

from pathlib import Path
from typing import Self, Any, Optional

from deployment_migration.application import (
    DeploymentMigration,
    FileHandler,
    VersionControl,
    Terraform,
    AWS,
    GithubActionsAuthor,
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
    ApplicationContext,
)


class StubFileHandler(FileHandler):
    """Stub implementation of FileHandler for testing."""

    def create_file(self: Self, path: Path, content: str) -> None:
        """Pretend to create a file."""
        return

    def read_file(self: Self, path: Path) -> str:
        """Pretend to read a file."""
        return '# Stub terraform configuration\n\nmodule "example" {\n  source = "example"\n  version = "1.0.0"\n}'

    def overwrite_file(self: Self, path: Path, content: str) -> None:
        """Pretend to overwrite a file."""
        return

    def folder_exists(self: Self, path: Path):
        """Pretend to check if a folder exists."""
        common_folders = [
            Path("terraform/template/"),
            Path("terraform/modules/template/"),
            Path("infrastructure/"),
            Path("terraform/environment/prod/"),
        ]
        return path in common_folders


class StubVersionControl(VersionControl):
    """Stub implementation of VersionControl for testing."""

    def commit(self: Self, message: str):
        """Pretend to commit changes."""
        return


class StubTerraformModifier(Terraform):
    """Stub implementation of TerraformModifyer for testing."""

    def update_module_versions(
        self: Self,
        terraform_config: str,
        target_modules: dict[str, str],
    ) -> str:
        """Pretend to update module versions."""
        return terraform_config + "\n# Stub: Updated module versions"

    def add_module(
        self: Self,
        terraform_config: str,
        name: str,
        source: str,
        version: str,
        variables: Optional[dict[str, Any]] = None,
    ) -> str:
        """Pretend to add a module."""
        return terraform_config + f"\n\n# Stub: Added module {name}"

    def has_module(
        self: Self, module_source: str, terraform_config: str = None
    ) -> bool:
        """Pretend to check if a module exists."""
        # For testing purposes, return True for specific module sources
        return module_source in [
            "https://github.com/nsbno/terraform-aws-lambda",
            "https://github.com/example/module",
        ]


class StubAWS(AWS):
    """Stub implementation of ParameterStore for testing."""

    def create_parameter(self: Self, name: str, value: str):
        """Pretend to create a parameter."""
        return


class StubGithubActionsAuthor(GithubActionsAuthor):
    """Stub implementation of GithubActionsAuthor for testing."""

    def create_deployment_workflow(
        self: Self,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: Path,
    ) -> str:
        return """name: Deploy
on:
  push:
    branches: [ main ]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy
        run: echo "Deploying..."
"""


class StubApplicationContext(ApplicationContext):
    """Stub implementation of ApplicationContext for testing."""

    def find_build_tool(self: Self) -> ApplicationBuildTool:
        """Return a stub build tool."""
        return ApplicationBuildTool.PYTHON

    def find_application_artifact_name(self: Self) -> list[str]:
        """Return a stub application name."""
        return ["stub-application"]


class StubDeploymentMigration(DeploymentMigration):
    """Stub implementation of DeploymentMigration for testing."""

    def find_application_name(self):
        """Return a stub application name."""
        names = self.application_context.find_application_artifact_name()
        return names[0]

    def find_build_tool(self):
        """Return a stub build tool."""
        return ApplicationBuildTool.PYTHON

    def find_aws_runtime(self):
        """Return a stub AWS runtime."""
        return ApplicationRuntimeTarget.LAMBDA

    def find_terraform_infrastructure_folder(self):
        """Return a stub terraform infrastructure folder."""
        return Path("terraform/template/")

    def find_terraform_environment_folder(self, environment: str):
        """Return a stub terraform environment folder."""
        return Path(f"terraform/environment/{environment}/")

    def upgrade_aws_repo_terraform_resources(self, terraform_folder: str):
        """Pretend to upgrade AWS repo terraform resources."""
        return

    def is_repo_in_clean_state(self):
        """Pretend to check if the repo is in a clean state."""
        return True


def create_stub_deployment_migration() -> DeploymentMigration:
    """Create a stub DeploymentMigration instance for testing."""
    return StubDeploymentMigration(
        version_control=StubVersionControl(),
        file_handler=StubFileHandler(),
        github_actions_author=StubGithubActionsAuthor(),
        terraform=StubTerraformModifier(),
        aws=StubAWS(),
        application_context=StubApplicationContext(),
    )
