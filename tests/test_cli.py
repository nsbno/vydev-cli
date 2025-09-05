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
    """Test successful application repo upgrade."""
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
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "rich.prompt.Prompt.ask",
        lambda *args, **kwargs: (
            "test-app"
            if "name" in args[0]
            else (
                ApplicationBuildTool.PYTHON
                if "build tool" in args[0]
                else (
                    ApplicationRuntimeTarget.LAMBDA
                    if "runtime" in args[0]
                    else "latest" if "version" in args[0] else str(terraform_folder)
                )
            )
        ),
    )

    # Call the method
    cli_handler.upgrade_application_repo()

    # Verify the deployment_migration methods were called
    mock_deployment_migration.upgrade_terraform_application_resources.assert_called_once_with(
        str(terraform_folder)
    )
    mock_deployment_migration.upgrade_application_repo_terraform_provider_versions.assert_called_once()
    mock_deployment_migration.create_github_action_deployment_workflow.assert_called_once()
    mock_deployment_migration.remove_old_deployment_setup.assert_called_once()

    # Verify console output
    output = string_io.getvalue()
    assert "Upgrade Application Repo" in output
    assert "Removing old deployment setup..." in output
    assert "Old deployment setup removed successfully!" in output
    assert "Upgrading application terraform resources..." in output
    assert "Application terraform resources upgraded successfully!" in output
    assert "Creating GitHub Actions deployment workflow..." in output
    assert "GitHub Actions workflow created successfully!" in output


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
