"""Tests for the ApplicationContextFinder class."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from deployment_migration.application import (
    ApplicationBuildTool,
    NotFoundError,
)
from deployment_migration.infrastructure.application_context import (
    ApplicationContextFinder,
)


@pytest.fixture
def application_context():
    """Create an instance of ApplicationContextFinder for testing."""
    return ApplicationContextFinder()


class TestFindBuildTool:
    """Tests for the find_build_tool method."""

    def test_find_build_tool_gradle(self, application_context):
        """Test that Gradle is detected when a Gradle file exists."""
        with patch("os.path.isfile") as mock_isfile:
            # Mock that build.gradle exists
            mock_isfile.side_effect = lambda path: path == "build.gradle"
            
            # Call the method
            result = application_context.find_build_tool()
            
            # Assert the result
            assert result == ApplicationBuildTool.GRADLE
            
            # Verify that isfile was called with the expected arguments
            mock_isfile.assert_any_call("build.gradle")

    def test_find_build_tool_python(self, application_context):
        """Test that Python is detected when pyproject.toml exists."""
        with patch("os.path.isfile") as mock_isfile:
            # Mock that pyproject.toml exists but no Gradle files
            mock_isfile.side_effect = lambda path: path == "pyproject.toml"
            
            # Call the method
            result = application_context.find_build_tool()
            
            # Assert the result
            assert result == ApplicationBuildTool.PYTHON
            
            # Verify that isfile was called with the expected arguments
            mock_isfile.assert_any_call("pyproject.toml")

    def test_find_build_tool_not_found(self, application_context):
        """Test that NotFoundError is raised when no build tool is detected."""
        with patch("os.path.isfile") as mock_isfile:
            # Mock that no files exist
            mock_isfile.return_value = False
            
            # Call the method and expect an exception
            with pytest.raises(NotFoundError) as excinfo:
                application_context.find_build_tool()
            
            # Assert the exception message
            assert "Could not determine the build tool" in str(excinfo.value)


class TestFindApplicationArtifactName:
    """Tests for the find_application_artifact_name method."""

    def test_find_application_artifact_name_yml(self, application_context):
        """Test finding application names from config.yml."""
        config_content = """
        artifacts:
          - name: app1
          - name: app2
          - name: app3-infra
        """
        
        with patch("os.path.isfile") as mock_isfile, \
             patch("builtins.open", mock_open(read_data=config_content)):
            # Mock that .deployment/config.yml exists
            mock_isfile.side_effect = lambda path: str(path) == ".deployment/config.yml"
            
            # Call the method
            result = application_context.find_application_artifact_name()
            
            # Assert the result (should exclude app3-infra)
            assert result == ["app1", "app2"]
            
            # Verify that isfile was called with the expected arguments
            mock_isfile.assert_any_call(Path(".deployment/config.yml"))

    def test_find_application_artifact_name_yaml(self, application_context):
        """Test finding application names from config.yaml."""
        config_content = """
        artifacts:
          - name: app1
          - name: app2-tf
        """
        
        with patch("os.path.isfile") as mock_isfile, \
             patch("builtins.open", mock_open(read_data=config_content)):
            # Mock that .deployment/config.yaml exists but not config.yml
            mock_isfile.side_effect = lambda path: str(path) == ".deployment/config.yaml"
            
            # Call the method
            result = application_context.find_application_artifact_name()
            
            # Assert the result (should exclude app2-tf)
            assert result == ["app1"]
            
            # Verify that isfile was called with the expected arguments
            mock_isfile.assert_any_call(Path(".deployment/config.yml"))
            mock_isfile.assert_any_call(Path(".deployment/config.yaml"))

    def test_find_application_artifact_name_no_config_file(self, application_context):
        """Test that FileNotFoundError is raised when no config file is found."""
        with patch("os.path.isfile") as mock_isfile:
            # Mock that no config files exist
            mock_isfile.return_value = False
            
            # Call the method and expect an exception
            with pytest.raises(FileNotFoundError) as excinfo:
                application_context.find_application_artifact_name()
            
            # Assert the exception message
            assert "Could not find .deployment/config.yml or config.yaml" in str(excinfo.value)

    def test_find_application_artifact_name_no_artifacts(self, application_context):
        """Test that NotFoundError is raised when no artifacts section is found."""
        config_content = """
        # No artifacts section
        something_else: value
        """
        
        with patch("os.path.isfile") as mock_isfile, \
             patch("builtins.open", mock_open(read_data=config_content)):
            # Mock that .deployment/config.yml exists
            mock_isfile.side_effect = lambda path: str(path) == ".deployment/config.yml"
            
            # Call the method and expect an exception
            with pytest.raises(NotFoundError) as excinfo:
                application_context.find_application_artifact_name()
            
            # Assert the exception message
            assert "No artifacts section found in the config file" in str(excinfo.value)

    def test_find_application_artifact_name_empty_artifacts(self, application_context):
        """Test finding application names when artifacts section is empty."""
        config_content = """
        artifacts: []
        """
        
        with patch("os.path.isfile") as mock_isfile, \
             patch("builtins.open", mock_open(read_data=config_content)):
            # Mock that .deployment/config.yml exists
            mock_isfile.side_effect = lambda path: str(path) == ".deployment/config.yml"
            
            # Call the method
            result = application_context.find_application_artifact_name()
            
            # Assert the result (should be an empty list)
            assert result == []