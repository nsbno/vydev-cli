import os
from pathlib import Path
from typing import Self

import yaml

from deployment_migration.application import (
    ApplicationContext,
    ApplicationBuildTool,
    NotFoundError,
)


class ApplicationContextFinder(ApplicationContext):
    def find_build_tool(self: Self) -> ApplicationBuildTool:
        """
        Determines the build tool used by the application by checking for specific files.

        Returns:
            ApplicationBuildTool: GRADLE if gradle files are found, PYTHON if pyproject.toml is found

        Raises:
            NotFoundError: If no build tool can be determined
        """
        gradle_files = [
            "build.gradle",
            "settings.gradle",
            "gradlew",
            "gradle.properties",
        ]
        for file in gradle_files:
            if os.path.isfile(file):
                return ApplicationBuildTool.GRADLE

        if os.path.isfile("pyproject.toml"):
            return ApplicationBuildTool.PYTHON

        raise NotFoundError(
            "Could not determine the build tool. No Gradle files or pyproject.toml found."
        )

    def find_application_artifact_name(self: Self) -> list[str]:
        """
        Finds the application name by reading the .deployment/config.yml or config.yaml file.

        Returns:
            list[str]: The application names

        Raises:
            NotFoundError: If no application name can be found
            FileNotFoundError: If the config file cannot be found
        """
        # Check for config files
        config_paths = [Path(".deployment/config.yml"), Path(".deployment/config.yaml")]

        config_file = next((path for path in config_paths if os.path.isfile(path)), None)
        if not config_file:
            raise FileNotFoundError(
                "Could not find .deployment/config.yml or config.yaml"
            )

        # Read and parse the config file
        with open(config_file, "r") as file:
            config = yaml.safe_load(file)

        if not config or "artifacts" not in config:
            raise NotFoundError("No artifacts section found in the config file")

        # Extract application names from artifacts
        app_names = [
            artifact.get("name")
            for artifact in config["artifacts"]
            if "name" in artifact
        ]

        without_infra = [
            app_name
            for app_name in app_names
            if not (app_name.endswith("-infra") or app_name.endswith("-tf"))
        ]

        return without_infra
