import io
import sys
import pytest
from unittest import mock
from pathlib import Path

from rich.console import Console

from deployment_migration.handlers.cli import CLIHandler, main
from deployment_migration.application import (
    DeploymentMigration,
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
)


@pytest.fixture
def mock_deployment_migration():
    """Create a mock DeploymentMigration instance."""
    return mock.Mock(spec=DeploymentMigration)


@pytest.fixture
def string_io():
    """Create a StringIO instance for capturing console output."""
    return io.StringIO()


@pytest.fixture
def console(string_io):
    """Create a Rich console that writes to StringIO."""
    return Console(file=string_io, highlight=False)


@pytest.fixture
def cli_handler(mock_deployment_migration, console):
    """Create a CLIHandler instance with mock dependencies."""
    return CLIHandler(deployment_migration=mock_deployment_migration, console=console)


def test_upgrade_aws_repo_success(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Test successful AWS repo upgrade."""
    # Mock rich.prompt.Prompt.ask and rich.prompt.Confirm.ask directly
    monkeypatch.setattr(
        "rich.prompt.Prompt.ask", lambda *args, **kwargs: "terraform/test"
    )
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *args, **kwargs: True)

    # Call the method
    cli_handler.upgrade_aws_repo()

    # Verify the deployment_migration method was called with correct args
    mock_deployment_migration.upgrade_aws_repo_terraform_resources.assert_called_with(
        "terraform/test"
    )

    # Verify console output
    output = string_io.getvalue()
    assert "Upgrade AWS Repo" in output
    assert "Upgrading AWS repo..." in output
    assert "AWS repo upgraded successfully!" in output


def test_upgrade_aws_repo_error(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Test AWS repo upgrade with error."""
    # Mock error in deployment_migration
    mock_deployment_migration.upgrade_aws_repo_terraform_resources.side_effect = (
        Exception("Test error")
    )

    # Mock rich.prompt.Prompt.ask and rich.prompt.Confirm.ask directly instead of patching input
    monkeypatch.setattr(
        "rich.prompt.Prompt.ask", lambda *args, **kwargs: "terraform/test"
    )
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *args, **kwargs: True)

    # Call the method and expect an exception
    with pytest.raises(Exception, match="Test error"):
        cli_handler.upgrade_aws_repo()

    # Verify console output
    output = string_io.getvalue()
    assert "Upgrade AWS Repo" in output
    assert "Upgrading AWS repo..." in output


def test_upgrade_application_repo_success(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Test successful application repo upgrade with new two-stage flow."""
    # Mock user inputs and deployment_migration methods
    terraform_folder = Path("terraform/template")
    mock_deployment_migration.find_terraform_infrastructure_folder.return_value = (
        terraform_folder
    )
    mock_deployment_migration.find_application_name.return_value = "test-app"
    mock_deployment_migration.find_build_tool.return_value = ApplicationBuildTool.PYTHON
    mock_deployment_migration.find_aws_runtime.return_value = (
        ApplicationRuntimeTarget.LAMBDA
    )
    mock_deployment_migration.find_all_environment_folders.return_value = []
    mock_deployment_migration.changed_files.return_value = [
        ".github/workflows/build-and-deploy.yml"
    ]

    # Mock generate_deployment_workflow
    mock_deployment_migration.generate_deployment_workflow = mock.Mock()

    # Mock rich.prompt.Prompt.ask and rich.prompt.Confirm.ask directly
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *args, **kwargs: True)

    def mock_prompt(*args, **kwargs):
        prompt = args[0].lower()
        if "service account" in prompt or "account id" in prompt:
            return "123456789012"
        elif "name" in prompt:
            return "test-app"
        elif "build tool" in prompt:
            return ApplicationBuildTool.PYTHON
        elif "runtime" in prompt:
            return ApplicationRuntimeTarget.LAMBDA
        else:
            return str(terraform_folder)

    monkeypatch.setattr("rich.prompt.Prompt.ask", mock_prompt)

    # Call the method
    cli_handler.upgrade_application_repo()

    # Verify the deployment_migration methods were called
    mock_deployment_migration.upgrade_terraform_application_resources.assert_called_once_with(
        str(terraform_folder)
    )
    mock_deployment_migration.upgrade_application_repo_terraform_provider_versions.assert_called_once()
    mock_deployment_migration.replace_image_with_ecr_repository_url.assert_called_once()
    mock_deployment_migration.generate_deployment_workflow.assert_called_once()
    mock_deployment_migration.remove_old_deployment_setup.assert_called_once()

    # Verify environment setup methods were NOT called (done in prepare)
    mock_deployment_migration.initialize_github_environments.assert_not_called()
    mock_deployment_migration.help_with_github_environment_setup.assert_not_called()

    # Verify console output includes new git instructions
    output = string_io.getvalue()
    assert "Branch Required" in output
    assert "Upgrade Application Repo" in output
    assert "Migration Complete" in output
    assert "git add ." in output
    assert "git commit -m" in output
    assert "git push -u origin migrate-to-github-actions" in output


def test_upgrade_application_repo_folder_not_found(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Test application repo upgrade when folder is not found."""
    # Mock error in finding terraform folder
    mock_deployment_migration.find_terraform_infrastructure_folder.side_effect = (
        FileNotFoundError("Folder not found")
    )

    # Mock other deployment_migration methods
    mock_deployment_migration.find_application_name.return_value = "test-app"
    mock_deployment_migration.find_build_tool.return_value = ApplicationBuildTool.PYTHON
    mock_deployment_migration.find_aws_runtime.return_value = (
        ApplicationRuntimeTarget.LAMBDA
    )
    mock_deployment_migration.find_all_environment_folders.return_value = [
        "dev",
        "test",
        "prod",
    ]
    mock_deployment_migration.help_with_github_environment_setup.return_value = (
        "https://github.com/org/repo/settings/environments",
        "github.com/nsbno/infrademo-jvm-app",
        {"dev": "123456789012"},
    )

    # Mock rich.prompt.Prompt.ask and rich.prompt.Confirm.ask directly
    # This is necessary because input() returns strings, but we need enum objects for some values
    terraform_folder = "terraform/template"

    # Set up a more complex mock for Prompt.ask to handle different prompts
    def mock_prompt_ask(*args, **kwargs):
        prompt = args[0]
        if "folder" in prompt:
            return terraform_folder
        elif "name" in prompt:
            return "test-app"
        elif "build tool" in prompt:
            return ApplicationBuildTool.PYTHON
        elif "runtime" in prompt:
            return ApplicationRuntimeTarget.LAMBDA
        else:
            return "latest"

    # Set up a mock for Confirm.ask to handle different prompts
    def mock_confirm_ask(*args, **kwargs):
        prompt = args[0]
        if "GitHub Actions" in prompt or "parameter store" in prompt:
            return False
        return True

    monkeypatch.setattr("rich.prompt.Prompt.ask", mock_prompt_ask)
    monkeypatch.setattr("rich.prompt.Confirm.ask", mock_confirm_ask)

    # Call the method
    cli_handler.upgrade_application_repo()

    # Verify the deployment_migration methods were called with manually entered folder
    mock_deployment_migration.upgrade_terraform_application_resources.assert_called_once_with(
        terraform_folder
    )

    # Verify console output
    output = string_io.getvalue()
    assert "Upgrade Application Repo" in output
    assert "Upgrading application terraform resources..." in output


def test_main_aws_operation(monkeypatch, string_io):
    """Test main function with aws operation."""
    # Mock sys.argv
    monkeypatch.setattr(sys, "argv", ["cli.py", "aws"])

    # Mock dependencies
    mock_cli_handler = mock.Mock(spec=CLIHandler)
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.CLIHandler",
        lambda *args, **kwargs: mock_cli_handler,
    )

    # Mock Console to use StringIO
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.Console",
        lambda *args, **kwargs: Console(file=string_io, highlight=False),
    )

    # Call main
    main()

    # Verify the correct method was called
    mock_cli_handler.upgrade_aws_repo.assert_called_once()
    mock_cli_handler.upgrade_application_repo.assert_not_called()


def test_main_application_operation(monkeypatch, string_io):
    """Test main function with application operation."""
    # Mock sys.argv
    monkeypatch.setattr(sys, "argv", ["cli.py", "application"])

    # Mock dependencies
    mock_cli_handler = mock.Mock(spec=CLIHandler)
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.CLIHandler",
        lambda *args, **kwargs: mock_cli_handler,
    )

    # Mock Console to use StringIO
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.Console",
        lambda *args, **kwargs: Console(file=string_io, highlight=False),
    )

    # Call main
    main()

    # Verify the correct method was called
    mock_cli_handler.upgrade_application_repo.assert_called_once()
    mock_cli_handler.upgrade_aws_repo.assert_not_called()


def test_main_invalid_operation(monkeypatch, string_io):
    """Test main function with invalid operation."""
    # Mock sys.argv
    monkeypatch.setattr(sys, "argv", ["cli.py", "invalid"])

    # Mock dependencies
    mock_cli_handler = mock.Mock(spec=CLIHandler)
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.CLIHandler",
        lambda *args, **kwargs: mock_cli_handler,
    )

    # Mock Console to use StringIO
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.Console",
        lambda *args, **kwargs: Console(file=string_io, highlight=False),
    )

    # Call main
    main()

    # Verify no methods were called
    mock_cli_handler.upgrade_aws_repo.assert_not_called()
    mock_cli_handler.upgrade_application_repo.assert_not_called()

    # Verify error message
    output = string_io.getvalue()
    assert "Error: Invalid argument 'invalid'" in output


def test_main_no_arguments(monkeypatch, string_io):
    """Test main function with no arguments."""
    # Mock sys.argv
    monkeypatch.setattr(sys, "argv", ["cli.py"])

    # Mock dependencies
    mock_cli_handler = mock.Mock(spec=CLIHandler)
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.CLIHandler",
        lambda *args, **kwargs: mock_cli_handler,
    )

    # Mock Console to use StringIO
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.Console",
        lambda *args, **kwargs: Console(file=string_io, highlight=False),
    )

    # Call main
    main()

    # Verify no methods were called
    mock_cli_handler.upgrade_aws_repo.assert_not_called()
    mock_cli_handler.upgrade_application_repo.assert_not_called()

    # Verify error message
    output = string_io.getvalue()
    assert "Error: Missing argument" in output


def test_prepare_migration_generates_pr_workflows(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Test prepare command generates PR workflows only."""
    # Mock user inputs
    terraform_folder = Path("terraform/template")
    mock_deployment_migration.find_terraform_infrastructure_folder.return_value = (
        terraform_folder
    )
    mock_deployment_migration.find_application_name.return_value = "test-app"
    mock_deployment_migration.find_build_tool.return_value = ApplicationBuildTool.PYTHON
    mock_deployment_migration.find_aws_runtime.return_value = (
        ApplicationRuntimeTarget.ECS
    )
    mock_deployment_migration.changed_files.return_value = [
        ".github/workflows/pull-request.yml",
        ".github/workflows/pull-request-comment.yml",
    ]

    # Mock environment setup
    mock_deployment_migration.find_all_environment_folders.return_value = [
        Path("terraform/dev"),
        Path("terraform/test"),
        Path("terraform/prod"),
    ]
    mock_deployment_migration.help_with_github_environment_setup.return_value = (
        "https://github.com/org/repo/settings/environments",
        "github.com/org/repo",
        {"Dev": "111111111111", "Test": "222222222222", "Prod": "333333333333"},
    )

    # Mock the generate_pr_workflows method
    mock_deployment_migration.generate_pr_workflows = mock.Mock()

    # Mock prompts and confirm
    def mock_prompt(*args, **kwargs):
        prompt_text = args[0] if args else ""
        if "name" in prompt_text:
            return "test-app"
        elif "build tool" in prompt_text:
            return ApplicationBuildTool.PYTHON
        elif "runtime" in prompt_text:
            return ApplicationRuntimeTarget.ECS
        elif "service account" in prompt_text.lower():
            return "444444444444"  # Service account ID
        else:
            return str(terraform_folder)

    monkeypatch.setattr("rich.prompt.Prompt.ask", mock_prompt)
    monkeypatch.setattr("shutil.which", lambda x: True)  # gh CLI is available
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *args, **kwargs: True)

    # Call the method
    cli_handler.prepare_migration()

    # Verify only PR workflows were generated (not full deployment)
    mock_deployment_migration.generate_pr_workflows.assert_called_once()
    mock_deployment_migration.create_github_action_deployment_workflow.assert_not_called()

    # Verify GitHub environments were initialized (includes Service environment)
    mock_deployment_migration.initialize_github_environments.assert_called_once_with(
        {
            "Dev": "111111111111",
            "Test": "222222222222",
            "Prod": "333333333333",
            "Service": "444444444444",
        },
        "github.com/org/repo",
    )

    # Verify changed files are displayed
    output = string_io.getvalue()
    assert "Setup PR Workflows" in output
    assert "Setting up GitHub Environments" in output
    assert ".github/workflows/pull-request.yml" in output
    assert ".github/workflows/pull-request-comment.yml" in output
    assert "Please commit and push these changes to main branch" in output


def test_main_prepare_operation(monkeypatch, string_io):
    """Test main function with prepare operation."""
    # Mock sys.argv
    monkeypatch.setattr(sys, "argv", ["cli.py", "prepare"])

    # Mock dependencies
    mock_cli_handler = mock.Mock(spec=CLIHandler)
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.CLIHandler",
        lambda *args, **kwargs: mock_cli_handler,
    )

    # Mock Console to use StringIO
    monkeypatch.setattr(
        "deployment_migration.handlers.cli.Console",
        lambda *args, **kwargs: Console(file=string_io, highlight=False),
    )

    # Call main
    main()

    # Verify the correct method was called
    mock_cli_handler.prepare_migration.assert_called_once()
    mock_cli_handler.upgrade_aws_repo.assert_not_called()
    mock_cli_handler.upgrade_application_repo.assert_not_called()


def test_upgrade_application_repo_shows_branch_reminder(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Should show branch reminder and exit if user says no."""
    # Mock user says NO to branch confirmation
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *args, **kwargs: False)

    # Call the method
    cli_handler.upgrade_application_repo()

    # Verify console output
    output = string_io.getvalue()
    assert "Branch Required" in output
    assert "git checkout -b migrate-to-github-actions" in output
    assert "Please create a migration branch first" in output

    # Should NOT proceed with migration
    mock_deployment_migration.upgrade_terraform_application_resources.assert_not_called()


def test_upgrade_application_repo_skips_environment_setup(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Should NOT set up GitHub environments (already done in prepare)."""
    # Mock user inputs and deployment_migration methods
    terraform_folder = Path("terraform/template")
    mock_deployment_migration.find_terraform_infrastructure_folder.return_value = (
        terraform_folder
    )
    mock_deployment_migration.find_application_name.return_value = "test-app"
    mock_deployment_migration.find_build_tool.return_value = ApplicationBuildTool.PYTHON
    mock_deployment_migration.find_aws_runtime.return_value = (
        ApplicationRuntimeTarget.LAMBDA
    )
    mock_deployment_migration.find_all_environment_folders.return_value = []

    # Mock prompts - user confirms branch
    def mock_confirm_ask(*args, **kwargs):
        # First call is for branch confirmation
        return True

    def mock_prompt_ask(*args, **kwargs):
        prompt = args[0]
        if "name" in prompt.lower():
            return "test-app"
        elif "build tool" in prompt.lower():
            return ApplicationBuildTool.PYTHON
        elif "runtime" in prompt.lower():
            return ApplicationRuntimeTarget.LAMBDA
        else:
            return str(terraform_folder)

    monkeypatch.setattr("rich.prompt.Confirm.ask", mock_confirm_ask)
    monkeypatch.setattr("rich.prompt.Prompt.ask", mock_prompt_ask)

    # Call the method
    cli_handler.upgrade_application_repo()

    # Should NOT call environment setup methods
    mock_deployment_migration.initialize_github_environments.assert_not_called()
    mock_deployment_migration.help_with_github_environment_setup.assert_not_called()


def test_upgrade_application_repo_generates_only_deployment_workflow(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Should only generate deployment workflow, not PR workflows."""
    # Mock user inputs and deployment_migration methods
    terraform_folder = Path("terraform/template")
    mock_deployment_migration.find_terraform_infrastructure_folder.return_value = (
        terraform_folder
    )
    mock_deployment_migration.find_application_name.return_value = "test-app"
    mock_deployment_migration.find_build_tool.return_value = ApplicationBuildTool.PYTHON
    mock_deployment_migration.find_aws_runtime.return_value = (
        ApplicationRuntimeTarget.ECS
    )
    mock_deployment_migration.find_all_environment_folders.return_value = []
    mock_deployment_migration.changed_files.return_value = [
        ".github/workflows/build-and-deploy.yml"
    ]

    # Add generate_deployment_workflow mock
    mock_deployment_migration.generate_deployment_workflow = mock.Mock()

    # Mock prompts
    def mock_confirm_ask(*args, **kwargs):
        return True

    def mock_prompt_ask(*args, **kwargs):
        prompt = args[0]
        if "name" in prompt.lower():
            return "test-app"
        elif "build tool" in prompt.lower():
            return ApplicationBuildTool.PYTHON
        elif "runtime" in prompt.lower():
            return ApplicationRuntimeTarget.ECS
        else:
            return str(terraform_folder)

    monkeypatch.setattr("rich.prompt.Confirm.ask", mock_confirm_ask)
    monkeypatch.setattr("rich.prompt.Prompt.ask", mock_prompt_ask)

    # Call the method
    cli_handler.upgrade_application_repo()

    # Should call generate_deployment_workflow, not create_github_action_deployment_workflow
    mock_deployment_migration.generate_deployment_workflow.assert_called_once()
    mock_deployment_migration.generate_pr_workflows.assert_not_called()


def test_upgrade_application_repo_shows_git_instructions(
    cli_handler, mock_deployment_migration, string_io, monkeypatch
):
    """Should show manual git instructions at the end."""
    # Mock user inputs and deployment_migration methods
    terraform_folder = Path("terraform/template")
    mock_deployment_migration.find_terraform_infrastructure_folder.return_value = (
        terraform_folder
    )
    mock_deployment_migration.find_application_name.return_value = "test-app"
    mock_deployment_migration.find_build_tool.return_value = ApplicationBuildTool.PYTHON
    mock_deployment_migration.find_aws_runtime.return_value = (
        ApplicationRuntimeTarget.LAMBDA
    )
    mock_deployment_migration.find_all_environment_folders.return_value = []
    mock_deployment_migration.changed_files.return_value = [
        ".github/workflows/build-and-deploy.yml"
    ]

    # Mock prompts
    def mock_confirm_ask(*args, **kwargs):
        return True

    def mock_prompt_ask(*args, **kwargs):
        prompt = args[0]
        if "name" in prompt.lower():
            return "test-app"
        elif "build tool" in prompt.lower():
            return ApplicationBuildTool.PYTHON
        elif "runtime" in prompt.lower():
            return ApplicationRuntimeTarget.LAMBDA
        else:
            return str(terraform_folder)

    monkeypatch.setattr("rich.prompt.Confirm.ask", mock_confirm_ask)
    monkeypatch.setattr("rich.prompt.Prompt.ask", mock_prompt_ask)

    # Call the method
    cli_handler.upgrade_application_repo()

    # Verify git instructions in output
    output = string_io.getvalue()
    assert "Migration Complete" in output
    assert "Next Steps" in output
    assert "git add ." in output
    assert "git commit -m" in output
    assert "git push -u origin migrate-to-github-actions" in output
    assert "Create a Pull Request on GitHub" in output
