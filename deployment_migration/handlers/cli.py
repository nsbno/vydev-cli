"""Command-line interface for the deployment migration application."""

import shutil
import sys
import argparse
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from deployment_migration.application import (
    DeploymentMigration,
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
    NotFoundError,
)
from deployment_migration.infrastructure.file_handler import (
    LocalFileHandler,
)
from deployment_migration.infrastructure.github_actions_author import (
    YAMLGithubActionsAuthor,
)
from deployment_migration.infrastructure.github_api import GithubApiImplementation
from deployment_migration.infrastructure.parameter_store import (
    AWSAWS,
)
from deployment_migration.infrastructure.terraform_modifier import (
    RegexTerraformModifier,
)
from deployment_migration.infrastructure.version_control import (
    GitVersionControl,
)
from deployment_migration.infrastructure.stub_handler import (
    create_stub_deployment_migration,
)
from deployment_migration.infrastructure.application_context import (
    ApplicationContextFinder,
)


class Terminal:
    pass


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

    def check_repo_clean_state(self) -> bool:
        """
        Check if the repository is in a clean state.

        If not, prompt the user to clean the git state before continuing.

        Returns:
            bool: True if the repository is in a clean state or the user wants to continue anyway,
                  False if the user wants to abort.
        """
        if not self.deployment_migration.is_repo_in_clean_state():
            self.console.print(
                "[bold yellow]Warning: The git repository has uncommitted changes.[/bold yellow]"
            )
            self.console.print(
                "It is recommended to commit or stash your existing changes before proceeding."
            )
            return Confirm.ask("Do you want to continue anyway?")
        return True

    def upgrade_aws_repo(self) -> None:
        """
        Handle the AWS repo upgrade operation.
        """
        if not self.deployment_migration.is_aws_repo():
            self.console.print(
                "[bold yellow]"
                "Warning: This repo doesn't end with `-aws`."
                "[/bold yellow]\n"
                "This is just a safety check to make sure you're not upgrading the wrong repo."
            )
            if not Confirm.ask("Is this repo your team's AWS repo?"):
                self.console.print(
                    "\n"
                    "Ok, aborting!\n"
                    "Just start the tool again when you are in the right repo."
                )
                return

        self.console.print(Panel("[bold]Upgrade AWS Repo[/bold]"))

        # Get terraform folder from user
        try:
            guessed_terraform_folder = (
                self.deployment_migration.find_terraform_infrastructure_folder()
            )
        except FileNotFoundError:
            guessed_terraform_folder = None
        terraform_infrastructure_folder = Prompt.ask(
            "Enter the terraform template/infrastrcuture folder path",
            default=(
                str(guessed_terraform_folder) if guessed_terraform_folder else None
            ),
        )

        try:
            guessed_terraform_service_folder = (
                self.deployment_migration.find_terraform_environment_folder("service")
            )
        except FileNotFoundError:
            guessed_terraform_service_folder = None
        terraform_service_folder = Prompt.ask(
            "Enter the terraform service environment folder path",
            default=(
                str(guessed_terraform_service_folder)
                if guessed_terraform_service_folder
                else None
            ),
        )

        self.console.print("\n[yellow]Upgrading AWS repo...[/yellow]")
        self.deployment_migration.upgrade_aws_repo_terraform_resources(
            terraform_infrastructure_folder
        )
        self.deployment_migration.upgrade_aws_repo_terraform_resources(
            terraform_service_folder
        )
        try:
            self.deployment_migration.upgrade_aws_repo_alb_resources(
                Path(terraform_infrastructure_folder)
            )
        except NotFoundError:
            self.console.print(
                "[yellow]"
                "ALB module was not found in the terraform infrastructure folder. "
                "Please migrate to it manually."
                "It can be found at: https://github.com/nsbno/terraform-aws-loadbalancer"
                "[/yellow]"
            )
            Confirm.ask("Have you migrated to using the ALB module?")
        self.console.print("[green]AWS repo upgraded successfully![/green]")

        changed_files = self.deployment_migration.changed_files()
        self.console.print(f"\nThe following files have changes: {changed_files}")
        self.console.print(
            "[bold]Please review, commit, and push the changes before proceeding.[/bold]"
        )

    def upgrade_application_repo(self) -> None:
        """
        Handle the application repo upgrade operation.
        """
        hr_line = Markdown("---")
        self.console.print(Panel("[bold]Upgrade Application Repo[/bold]"))

        # Guide the user through the environment setup process
        environment_folders = self.deployment_migration.find_all_environment_folders()
        new_env_url, repo_address, accounts = (
            self.deployment_migration.help_with_github_environment_setup(
                environment_folders
            )
        )

        if "Service" not in accounts:
            # Sometimes, the user might not have a service environment set up in the repo
            service_account_id = Prompt.ask(
                "What is the account ID of your service account?"
            )
            accounts["Service"] = service_account_id

        try:
            self.deployment_migration.find_environment_aws_profile_names()
        except NotFoundError as e:
            self.console.print(
                f"[bold red]Error: {e}[/bold red]\n"
                f"Please make sure you have set up AWS CLI profiles for all AWS environments.\n"
            )
            return

        # Try to find terraform infrastructure folder automatically
        try:
            terraform_folder = str(
                self.deployment_migration.find_terraform_infrastructure_folder()
            )
        except FileNotFoundError:
            terraform_folder = None

        if terraform_folder is None:
            self.console.print(
                "[italic blue]Hint: [/italic blue]"
                "[italic]Terraform infrastructure folder path is the parent directory of test, stage, service and prod[/italic]"
            )
        terraform_folder_str = Prompt.ask(
            "[bold]Enter the terraform infrastructure folder path[/bold]",
            default=terraform_folder,
        )
        terraform_folder = Path(terraform_folder_str)

        # TODO: Fix the split between application name and repo name
        try:
            guessed_repository_name = self.deployment_migration.find_application_name(
                terraform_folder
            )
        except NotFoundError:
            guessed_repository_name = None

        self.console.print(hr_line)
        if guessed_repository_name is None:
            self.console.print(
                "[italic blue]Hint: [/italic blue]"
                "[italic]ECR repo name can be found in the Terraform configuration.[/italic]"
            )
        repository_name = Prompt.ask(
            "[bold]What is the name of the service's ECR Repository?[/bold]",
            default=guessed_repository_name,
        )

        self.console.print(hr_line)
        self.console.print(
            "[italic blue]Hint: [/italic blue]"
            "[italic]Service name can be found in the Terraform file where the ECS service or Lambda function is defined.[/italic]"
        )
        application_name = Prompt.ask(
            "[bold]What is the service name?[/bold]"
        )

        try:
            guessed_build_tool = self.deployment_migration.find_build_tool()
        except NotFoundError:
            guessed_build_tool = None

        build_tool = None
        while build_tool is None:
            self.console.print(hr_line)
            build_tool = Prompt.ask(
                "Select the application build tool",
                choices=[ApplicationBuildTool.GRADLE, ApplicationBuildTool.PYTHON],
                default=guessed_build_tool,
            )

        try:
            guessed_target_runtime = self.deployment_migration.find_aws_runtime(
                terraform_folder
            )
        except NotFoundError:
            guessed_target_runtime = None
        runtime_target = None
        while runtime_target is None:
            self.console.print(hr_line)
            runtime_target = Prompt.ask(
                "Select the application runtime target",
                choices=[ApplicationRuntimeTarget.LAMBDA, ApplicationRuntimeTarget.ECS],
                default=guessed_target_runtime,
            )

        self.console.print(hr_line)
        if shutil.which("gh"):
            self.console.print(
                "GitHub CLI is installed, using it to create GH environments."
            )
            self.deployment_migration.initialize_github_environments(
                accounts, repo_address
            )
        else:
            self.console.print("\n[bold]Please complete the following steps:[/bold]")
            for env, account in accounts.items():
                self.console.print(
                    f"Visit {new_env_url} to set up the following environment:"
                )
                self.console.print(f"   - [italic]Name[/italic]: {env}")
                self.console.print(
                    f"   - [italic]Environment Variable[/italic]: AWS_ACCOUNT_ID={account}\n"
                )
                while not Confirm.ask("\nHave you created this environment in GH?"):
                    self.console.print(
                        "[bold red]Please complete the environment setup before continuing[/bold red]"
                    )

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

        self.console.print(
            "[yellow]Creating GitHub Actions deployment workflow...[/yellow]"
        )
        self.deployment_migration.create_github_action_deployment_workflow(
            repository_name,
            application_name,
            build_tool,
            runtime_target,
            terraform_folder,
        )
        self.console.print(
            "[green]GitHub Actions workflow created successfully![/green]"
        )

        # Remove old deployment setup
        self.console.print("[yellow]Removing old deployment setup...[/yellow]")
        self.deployment_migration.remove_old_deployment_setup()
        self.console.print("[green]Old deployment setup removed successfully![/green]")

        changed_files = self.deployment_migration.changed_files()
        self.console.print(f"\nThe following files have changes: {changed_files}")
        self.console.print(
            "[bold]Please review, commit and push the changes before proceeding.[/bold]"
        )


def main():
    """
    Main entry point for the CLI.

    Accepts command-line arguments to directly choose the operation:
    - 'aws': Upgrade AWS repo
    - 'application': Upgrade application repo

    Optional flags:
    - '--stub': Use stub implementations for testing

    Example usage:
    ./myscript.py aws
    ./myscript.py application
    ./myscript.py aws --stub
    ./myscript.py application --stub
    """
    console = Console()

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Deployment Migration CLI")
    parser.add_argument(
        "operation",
        choices=["aws", "application"],
        help="Operation to perform: 'aws' or 'application'",
    )
    parser.add_argument(
        "--stub", action="store_true", help="Use stub implementations for testing"
    )

    # Handle the case when no arguments are provided
    if len(sys.argv) < 2:
        console.print("[bold red]Error: Missing argument[/bold red]")
        parser.print_help()
        return

    try:
        args = parser.parse_args()
        operation = args.operation.lower()
        use_stub = args.stub
    except SystemExit:
        # Handle invalid operation
        console.print(f"[bold red]Error: Invalid argument '{sys.argv[1]}'[/bold red]")
        parser.print_help()
        return

    if use_stub:
        console.print("[yellow]Using stub implementation for testing[/yellow]")
        deployment_migration = create_stub_deployment_migration()
    else:
        # Create instances of the required dependencies
        file_handler = LocalFileHandler()
        github_actions_author = YAMLGithubActionsAuthor()
        parameter_store = AWSAWS()
        terraform_modifier = RegexTerraformModifier()
        version_control = GitVersionControl()
        application_context = ApplicationContextFinder()
        github_api = GithubApiImplementation()

        # Create an instance of DeploymentMigration
        deployment_migration = DeploymentMigration(
            version_control=version_control,
            file_handler=file_handler,
            github_actions_author=github_actions_author,
            terraform=terraform_modifier,
            aws=parameter_store,
            application_context=application_context,
            github_api=github_api,
        )

    console.print(
        Panel.fit(
            "[bold blue]Deployment Migration[/bold blue]\n\n"
            "Let's migrate to GitHub Actions 🚀"
        )
    )

    # Create an instance of CLIHandler
    cli_handler = CLIHandler(deployment_migration, console)

    # Check if the repository is in a clean state
    if not cli_handler.check_repo_clean_state():
        return

    # Run the appropriate operation
    if operation == "aws":
        cli_handler.upgrade_aws_repo()
    elif operation == "application":
        cli_handler.upgrade_application_repo()
    else:
        console.print(f"[bold red]Error: Invalid argument '{operation}'[/bold red]")
        parser.print_help()


if __name__ == "__main__":
    main()
