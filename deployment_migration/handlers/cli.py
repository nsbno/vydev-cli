"""Command-line interface for the deployment migration application."""

import shutil
import sys
import argparse
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from deployment_migration.application import (
    DeploymentMigration,
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
    NotFoundError,
)
from deployment_migration.handlers.view import Queryier, Terminal
from deployment_migration.infrastructure.file_handler import (
    LocalFileHandler,
)
from deployment_migration.infrastructure.github_actions_author import (
    YAMLGithubActionsAuthor,
)
from deployment_migration.infrastructure.github_api import GithubApiImplementation
from deployment_migration.infrastructure.aws import (
    AWSClient,
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


class CLIHandler:
    """
    Command-line interface handler for the deployment migration application.

    This class handles the CLI operations for upgrading AWS and application repositories.
    """

    def __init__(
        self,
        deployment_migration: DeploymentMigration,
        console: Console = None,
    ):
        """
        Initialize the CLI handler.

        Args:
            deployment_migration: DeploymentMigration instance to use for operations
            config_cache: ConfigCache instance for caching user answers
            console: Rich console for UI, creates a new one if not provided
        """
        self.deployment_migration = deployment_migration
        self.console = console or Console()
        self.terminal = Terminal(self.console)
        self.queryier = Queryier(self.terminal)

    def check_repo_clean_state(self) -> bool:
        """
        Check if the repository is in a clean state.

        If not, prompt the user to clean the git state before continuing.

        Returns:
            bool: True if the repository is in a clean state or the user wants to continue anyway,
                  False if the user wants to abort.
        """
        if not self.deployment_migration.is_repo_in_clean_state():
            self.terminal.warn(
                short="This repo is not in a clean state.",
                long=(
                    "It is recommended to commit or stash your "
                    "existing changes before proceeding."
                ),
            )
            return Confirm.ask("Do you want to continue anyway?")
        return True

    def upgrade_aws_repo(self) -> None:
        """
        Handle the AWS repo upgrade operation.
        """
        if not self.deployment_migration.is_aws_repo():
            self.terminal.warn(
                short="This repo doesn't end with `-aws`.",
                long=(
                    "This is just a safety check to make sure "
                    "you're not upgrading the wrong repo."
                ),
            )
            if not Confirm.ask("Is this repo your team's AWS repo?"):
                self.console.print(
                    "\n"
                    "Ok, aborting!\n"
                    "Just start the tool again when you are in the right repo."
                )
                return

        self.console.print(Panel("[bold]Upgrade AWS Repo[/bold]"))

        self.terminal.hr_line()

        # Get terraform folder from user
        terraform_infrastructure_folder = self.queryier.ask_user_with_default_and_hint(
            question="Where is the terraform infrastructure folder?",
            default_query=lambda: str(
                self.deployment_migration.find_terraform_infrastructure_folder(),
            ),
        )

        self.terminal.hr_line()

        terraform_service_folder = self.queryier.ask_user_with_default_and_hint(
            question="Where is the terraform service environment folder?",
            default_query=lambda: str(
                self.deployment_migration.find_terraform_environment_folder("service"),
            ),
        )

        self.terminal.update("Upgrading AWS Repo...")

        for folder in [terraform_service_folder, terraform_infrastructure_folder]:
            self.deployment_migration.upgrade_aws_repo_terraform_resources(folder)

        try:
            self.deployment_migration.upgrade_aws_repo_alb_resources(
                Path(terraform_infrastructure_folder)
            )
        except NotFoundError:
            self.console.print(
                "[yellow]"
                "ALB module was not found in the terraform infrastructure folder. "
                "Please upgrade to it manually."
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

    def prepare_migration(self) -> None:
        """
        Prepare upgrade by generating PR workflows.

        This is step 1 of the two-command upgrade flow. It generates
        pull-request.yml and pull-request-comment.yml workflows that
        allow testing the upgrade before full deployment.
        """
        self.terminal.heading_and_info(
            heading="Setup PR Workflows",
            info=(
                "This step will generate PR workflows "
                "that let you test all the upgrade changes safely "
                "using pull requests."
            ),
        )

        # Try to find terraform infrastructure folder automatically
        terraform_folder = self.queryier.ask_user_with_default_and_hint(
            question="Where is the terraform infrastructure folder?",
            hint="This is typically `template/`",
            default_query=lambda: str(
                self.deployment_migration.find_terraform_infrastructure_folder(),
            ),
        )

        repository_name = self.queryier.ask_user_with_default_and_hint(
            question="What is the name of the service's ECR Repository?",
            hint="ECR repo name is often found in the `service` environment of your -aws repo.",
            default_query=lambda: self.deployment_migration.find_application_name(
                Path(terraform_folder)
            ),
        )

        application_name = self.queryier.ask_user_with_default_and_hint(
            question="What is the service name?",
            hint="Service name can be found in the Terraform file where the ECS service or Lambda function is defined.",
            default_query=lambda: self.deployment_migration.find_application_name(
                Path(terraform_folder)
            ),
        )

        build_tool = ApplicationBuildTool.GRADLE
        runtime_target = ApplicationRuntimeTarget.ECS

        # Set up GitHub environments for PR workflows
        self.terminal.hr_line()
        self.terminal.update("Setting up GitHub Actions Environments...")

        environment_folders = self.deployment_migration.find_all_environment_folders()
        new_env_url, repo_address, accounts = (
            self.deployment_migration.help_with_github_environment_setup(
                environment_folders
            )
        )

        if "Service" not in accounts:
            service_account_id = self.queryier.ask_user_with_default_and_hint(
                question="What is the service account ID?",
                hint="You can typically find the ID by checking the login in the AWS console",
                default_query=lambda: None,
            )
            accounts["Service"] = service_account_id

        if shutil.which("gh"):
            self.terminal.update("Creating GitHub environments using gh CLI...")
            self.deployment_migration.initialize_github_environments(
                accounts, repo_address
            )
        else:
            self.console.print(
                "\n[bold yellow]GitHub CLI not found. Please create environments manually:[/bold yellow]"
            )
            for env, account in accounts.items():
                self.console.print(f"Visit {new_env_url} to set up:")
                self.console.print(f"   - [italic]Name[/italic]: {env}")
                self.console.print(
                    f"   - [italic]Environment Variable[/italic]: AWS_ACCOUNT_ID={account}\n"
                )
                while not Confirm.ask(f"\nHave you created the '{env}' environment?"):
                    self.console.print(
                        "[bold red]Please complete the environment setup before continuing[/bold red]"
                    )

        # Generate PR workflows
        self.terminal.update("Generating PR workflows...")
        self.deployment_migration.generate_pr_workflows(
            repository_name=repository_name,
            application_name=application_name,
            application_build_tool=build_tool,
            application_runtime_target=runtime_target,
            terraform_base_folder=terraform_folder,
        )
        self.console.print(
            "[green]GitHub Actions PR workflows created successfully![/green]"
        )

        # Show changed files
        changed_files = self.deployment_migration.changed_files()
        self.console.print(f"\nThe following files have changes: {changed_files}")

        self.console.print(
            "\n[bold]Please commit and push these changes to main branch before proceeding.[/bold]"
        )

        # Show completion panel
        self.console.print(Panel("[bold]✓ PR Workflows Ready![/bold]"))

        self.console.print(
            "\n[bold]Next Steps:[/bold]\n"
            "  1. Review the generated workflow files\n"
            "  2. Commit and push to main:\n"
            "     [cyan]git add .github/workflows/\n"
            '     git commit -m "Add GitHub Actions PR workflows"\n'
            "     git push[/cyan]\n"
            "  3. Run [cyan]'vydev application'[/cyan] to create the upgrade PR\n"
        )

    def upgrade_application_repo(self) -> None:
        """
        Handle the application repo upgrade operation.
        """
        self.terminal.heading_and_info(
            heading="Upgrade Application Repo",
            info=(
                "This step will upgrade the application repo to use GitHub Actions "
                "deployment workflows. It will also remove the old deployment setup."
            ),
        )

        terraform_folder = self.queryier.ask_user_with_default_and_hint(
            question="Where is the terraform infrastructure folder?",
            hint="This is typically `terraform/template/`",
            default_query=lambda: str(
                self.deployment_migration.find_terraform_infrastructure_folder(),
            ),
        )

        repository_name = self.queryier.ask_user_with_default_and_hint(
            question="What is the name of the service's ECR Repository?",
            hint="ECR repo name is often found in the `service` folder of your `-aws` repo.",
            default_query=lambda: self.deployment_migration.find_application_name(
                Path(terraform_folder)
            ),
        )

        application_name = self.queryier.ask_user_with_default_and_hint(
            question="What is the service name?",
            hint=f"Service name can typically be found in `{terraform_folder}/main.tf` under the ECS service module",
            default_query=lambda: self.deployment_migration.find_application_name(
                Path(terraform_folder)
            ),
        )

        build_tool = ApplicationBuildTool.GRADLE
        runtime_target = ApplicationRuntimeTarget.ECS

        # Get environment folders for later use
        environment_folders = self.deployment_migration.find_all_environment_folders()
        self.terminal.hr_line()
        github_repository_name = self.deployment_migration.get_github_repository_name()

        # Upgrade terraform resources
        self.console.print(
            "[yellow]Upgrading application terraform resources...[/yellow]"
        )
        self.deployment_migration.upgrade_application_repo_terraform_provider_versions(
            [str(v) for v in ([terraform_folder] + environment_folders)]
        )
        self.deployment_migration.upgrade_terraform_application_resources(
            str(terraform_folder)
        )
        self.deployment_migration.replace_image_with_ecr_repository_url(
            str(terraform_folder),
            repository_name,
            github_repository_name,
        )
        self.console.print(
            "[green]Application terraform resources upgraded successfully![/green]"
        )

        # PHASE 3: Generate only deployment workflow (PR workflows already exist)
        self.console.print(
            "[yellow]Creating GitHub Actions deployment workflow...[/yellow]"
        )
        self.deployment_migration.generate_deployment_workflow(
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

        # PHASE 4: Show manual git instructions
        changed_files = self.deployment_migration.changed_files()
        self.console.print(f"\nThe following files have changes: {changed_files}")

        self.terminal.hr_line()
        self.console.print("\n[bold green]✅ Migration Complete![/bold green]\n")
        self.console.print("[bold]Next Steps:[/bold]\n")
        self.console.print("1. Review the changes in your working directory")
        self.console.print("2. Commit the changes:")
        self.console.print("   [cyan]git add .[/cyan]")
        self.console.print(
            "   [cyan]git commit -m 'Upgrade to GitHub Actions deployment'[/cyan]\n"
        )
        self.console.print("3. Push to remote:")
        self.console.print("   [cyan]git push[/cyan]\n")


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
        choices=["aws", "application", "prepare"],
        help="Operation to perform: 'aws', 'application', or 'prepare'",
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
        aws_client = AWSClient()
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
            aws=aws_client,
            application_context=application_context,
            github_api=github_api,
        )

    # Ensure cache file is in .gitignore
    deployment_migration.ensure_cache_in_gitignore()

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
    elif operation == "prepare":
        cli_handler.prepare_migration()
    else:
        console.print(f"[bold red]Error: Invalid argument '{operation}'[/bold red]")
        parser.print_help()


if __name__ == "__main__":
    main()
