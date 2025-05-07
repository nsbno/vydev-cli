"""Command-line interface for the deployment migration application."""

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from deployment_migration.application import (
    DeploymentMigration,
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
)
from deployment_migration.infrastructure.file_handler import (
    LocalFileHandler,
)
from deployment_migration.infrastructure.github_actions_author import (
    YAMLGithubActionsAuthor,
)
from deployment_migration.infrastructure.parameter_store import (
    AWSParameterStore,
)
from deployment_migration.infrastructure.terraform_modifier import (
    RegexTerraformModifier,
)
from deployment_migration.infrastructure.version_control import (
    GitVersionControl,
)


class CLIHandler:
    """
    Command-line interface handler for the deployment migration application.

    This class handles the CLI operations for upgrading AWS and application repositories.
    """

    def __init__(
        self, deployment_migration: DeploymentMigration, console: Console = None
    ):
        """
        Initialize the CLI handler.

        Args:
            deployment_migration: DeploymentMigration instance to use for operations
            console: Rich console for UI, creates a new one if not provided
        """
        self.deployment_migration = deployment_migration
        self.console = console or Console()

    def upgrade_aws_repo(self) -> None:
        """
        Handle the AWS repo upgrade operation.
        """
        self.console.print(Panel("[bold]Upgrade AWS Repo[/bold]"))

        # Get terraform folder from user
        terraform_folder = Prompt.ask(
            "Enter the terraform folder path", default="terraform/environment/prod"
        )

        # Confirm before proceeding
        if Confirm.ask(
            f"Are you sure you want to upgrade the AWS repo at {terraform_folder}?"
        ):
            try:
                self.console.print("[yellow]Upgrading AWS repo...[/yellow]")
                self.deployment_migration.upgrade_aws_repo_terraform_resources(
                    terraform_folder
                )
                self.console.print("[green]AWS repo upgraded successfully![/green]")

                # TODO: Module URL and version are missing in application.py
                self.console.print(
                    "[yellow]Note: The module URL and version are currently empty in the implementation. "
                    "Please update them in application.py.[/yellow]"
                )
            except Exception as e:
                self.console.print(
                    f"[bold red]Error upgrading AWS repo: {str(e)}[/bold red]"
                )

    def upgrade_application_repo(self) -> None:
        """
        Handle the application repo upgrade operation.
        """
        self.console.print(Panel("[bold]Upgrade Application Repo[/bold]"))

        # Try to find terraform infrastructure folder automatically
        try:
            self.console.print(
                "[yellow]Trying to find terraform infrastructure folder...[/yellow]"
            )

            terraform_folder = (
                self.deployment_migration.find_terraform_infrastructure_folder()
            )
            self.console.print(
                f"[green]Found terraform infrastructure folder: {terraform_folder}[/green]"
            )

            if not Confirm.ask(f"Use the found terraform folder: {terraform_folder}?"):
                terraform_folder_str = Prompt.ask(
                    "Enter the terraform infrastructure folder path",
                    default=str(terraform_folder),
                )
                terraform_folder = Path(terraform_folder_str)
        except FileNotFoundError:
            terraform_folder_str = Prompt.ask(
                "Enter the terraform infrastructure folder path",
                default="terraform/template",
            )
            terraform_folder = Path(terraform_folder_str)

        # Get application details
        self.console.print("[yellow]Getting application details...[/yellow]")

        guessed_application_name = self.deployment_migration.find_application_name()
        application_name = Prompt.ask(
            "What is the name of this application?", default=guessed_application_name
        )

        guessed_build_tool = self.deployment_migration.find_build_tool()
        build_tool = Prompt.ask(
            "Select the application build tool",
            choices=[ApplicationBuildTool.GRADLE, ApplicationBuildTool.PYTHON],
            default=guessed_build_tool,
        )

        self.console.print(f"Selected build tool: [green]{build_tool.value}[/green]")

        guessed_target_runtime = self.deployment_migration.find_aws_runtime()
        runtime_target = Prompt.ask(
            "Select the application runtime target",
            choices=[ApplicationRuntimeTarget.LAMBDA, ApplicationRuntimeTarget.ECS],
            default=guessed_target_runtime,
        )
        self.console.print(
            f"Selected runtime target: [green]{runtime_target.value}[/green]"
        )

        # Confirm before proceeding
        if not Confirm.ask(
            f"Are you sure you want to upgrade the application repo at {terraform_folder}?"
        ):
            self.console.print("[bold red]Aborting upgrade[/bold red]")
            return

        try:
            # Upgrade terraform resources
            self.console.print(
                "[yellow]Upgrading application terraform resources...[/yellow]"
            )
            self.deployment_migration.upgrade_terraform_application_resources(
                str(terraform_folder)
            )
            self.console.print(
                "[green]Application terraform resources upgraded successfully![/green]"
            )

            # Create GitHub Actions workflow
            if Confirm.ask(
                "Do you want to create a GitHub Actions deployment workflow?"
            ):
                self.console.print(
                    "[yellow]Creating GitHub Actions deployment workflow...[/yellow]"
                )
                self.deployment_migration.create_github_action_deployment_workflow(
                    application_name,
                    build_tool,
                    runtime_target,
                    terraform_folder,
                )
                self.console.print(
                    "[green]GitHub Actions workflow created successfully![/green]"
                )

            # Create parameter store version parameter
            if Confirm.ask(
                "Do you want to create a parameter store version parameter?"
            ):
                self.console.print(
                    "[yellow]Creating parameter store version parameter...[/yellow]"
                )
                temp_version = Prompt.ask("Enter a temporary version", default="latest")
                self.deployment_migration.create_parameter_store_version_parameter(
                    application_name, temp_version
                )
                self.console.print(
                    "[green]Parameter store version parameter created successfully![/green]"
                )

        except Exception as e:
            self.console.print(
                f"[bold red]Error upgrading application repo: {str(e)}[/bold red]"
            )


def main():
    """
    Main entry point for the CLI.

    Accepts command-line arguments to directly choose the operation:
    - 'aws': Upgrade AWS repo
    - 'application': Upgrade application repo

    Example usage:
    ./myscript.py aws
    ./myscript.py application
    """
    console = Console()

    # Create instances of the required dependencies
    file_handler = LocalFileHandler()
    github_actions_author = YAMLGithubActionsAuthor()
    parameter_store = AWSParameterStore()
    terraform_modifier = RegexTerraformModifier()
    version_control = GitVersionControl()

    # Create an instance of DeploymentMigration
    deployment_migration = DeploymentMigration(
        version_control=version_control,
        file_handler=file_handler,
        github_actions_author=github_actions_author,
        terraform_modifier=terraform_modifier,
        parameter_store=parameter_store,
    )

    # Create an instance of CLIHandler
    cli_handler = CLIHandler(deployment_migration, console)

    # Check command-line arguments
    if len(sys.argv) < 2:
        console.print("[bold red]Error: Missing argument[/bold red]")
        console.print(f"Usage: ${sys.argv[0]} [aws|application]")
        return

    operation = sys.argv[1].lower()

    console.print(
        Panel.fit(
            "[bold blue]Deployment Migration[/bold blue]\n\n"
            "Let's migrate to GitHub Actions 🚀"
        )
    )

    # Run the appropriate operation
    if operation == "aws":
        cli_handler.upgrade_aws_repo()
    elif operation == "application":
        cli_handler.upgrade_application_repo()
    else:
        console.print(f"[bold red]Error: Invalid argument '{operation}'[/bold red]")
        console.print(f"Usage: ${sys.argv[0]} [aws|application]")


if __name__ == "__main__":
    main()
