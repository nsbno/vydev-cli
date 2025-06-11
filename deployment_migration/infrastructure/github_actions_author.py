from pathlib import Path

import yaml
from typing import Self, Dict, Any

from deployment_migration.application import (
    GithubActionsAuthor,
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
)


class YAMLGithubActionsAuthor(GithubActionsAuthor):
    """Implementation of GithubActionsAuthor that generates GitHub Actions workflow YAML files."""

    def _workflow(self, type: str, name: str, version: str) -> str:
        return f"nsbno/platform-actions/.github/workflows/{type}.{name}.yml@{version}"

    def _build_and_package(
        self,
        repository_name: str,
        build_tool: ApplicationBuildTool,
        runtime_target: ApplicationRuntimeTarget,
        add_tests: bool = True,
        dockerfile_path: str = None,
    ) -> dict[str, Any]:
        if build_tool == ApplicationBuildTool.GRADLE:
            build_step = {
                "build": {
                    "uses": self._workflow("build", "gradle", "main"),
                    "secrets": "inherit",
                }
            }
        elif build_tool == ApplicationBuildTool.PYTHON:
            build_step = {
                "build": {
                    "uses": self._workflow("build", build_tool, "main"),
                }
            }
        else:
            raise NotImplementedError(f"{build_tool} is currently not supported")

        test_step = {}
        if add_tests:
            test_step = {
                "test": {
                    "uses": self._workflow("test", "gradle", "main"),
                    "secrets": "inherit",
                }
            }

        if runtime_target == ApplicationRuntimeTarget.ECS:
            with_params = {
                "repo-name": repository_name,
                "artifact-name": "${{ needs.build.outputs.artifact-name }}",
                "artifact-path": "${{ needs.build.outputs.artifact-path }}",
            }

            if dockerfile_path and dockerfile_path != Path("Dockerfile"):
                with_params["dockerfile"] = dockerfile_path

            package_step = {
                "package": {
                    "uses": self._workflow("package", "docker", "main"),
                    "needs": ["build", *(["test"] if add_tests else [])],
                    "secrets": "inherit",
                    "with": with_params,
                }
            }
        elif runtime_target == ApplicationRuntimeTarget.LAMBDA:
            package_step = {
                "package": {
                    "needs": ["build", *(["test"] if add_tests else [])],
                    "uses": self._workflow("package", "s3", "main"),
                    "secrets": "inherit",
                    "with": {
                        "repo-name": repository_name,
                        "artifact-name": "${{ needs.build.outputs.artifact-name }}",
                        "artifact-path": "${{ needs.build.outputs.artifact-path }}",
                        "directory-to-zip": "${{ needs.build.outputs.artifact-path }}",
                    },
                }
            }
        else:
            raise NotImplementedError(f"{runtime_target} is currently not supported")

        return {**build_step, **test_step, **package_step}

    def create_pull_request_workflow(
        self: Self,
        repository_name: str,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: Path,
        dockerfile_path: str = None,
    ) -> str:
        """
        Create a GitHub Actions pull request workflow for the application.
        """
        jobs = self._build_and_package(
            repository_name,
            application_build_tool,
            application_runtime_target,
            dockerfile_path=dockerfile_path,
        )
        jobs.pop("package")

        jobs["terraform-plan"] = {
            "uses": self._workflow("helpers", "terraform-plan", "main"),
            "secrets": "inherit",
        }

        workflow: Dict[str, Any] = {
            "name": "🔨 Pull Request 🔨",
            "on": ["pull_request"],
            "jobs": jobs,
        }

        # Convert the workflow to YAML
        yaml_string = yaml.dump(workflow, sort_keys=False)

        return yaml_string

    def create_deployment_workflow(
        self: Self,
        repository_name: str,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: Path,
        dockerfile_path: str = None,
    ) -> str:
        """
        Create a GitHub Actions deployment workflow for the application.

        :param application_name: The name of the application
        :param application_build_tool: The build tool used by the application (PYTHON or GRADLE)
        :param application_runtime_target: The runtime target for the application (LAMBDA or ECS)
        :param terraform_base_folder: The base folder for Terraform configuration
        :param dockerfile_path: The path to the Dockerfile to use for building the Docker image
        :return: The GitHub Actions workflow as a YAML string
        """
        jobs = {
            "terraform-changes": {
                "uses": self._workflow("helpers.find-changes", "terraform", "main"),
                "secrets": "inherit",
            },
            **self._build_and_package(
                repository_name,
                application_build_tool,
                application_runtime_target,
                dockerfile_path=dockerfile_path,
            ),
        }

        # Add the deploy job with dynamic needs
        jobs["deploy"] = {
            "needs": [name for name in jobs.keys()],
            "uses": self._workflow("deployment", "all-environments", "main"),
            "secrets": "inherit",
            "if": "!cancelled() && !contains(needs.*.results, 'failure') && success()",
            "with": {
                "applications": application_name,
                "terraform-changes": "${{ needs.terraform-changes.outputs.has-changes }}",
            },
        }

        workflow: Dict[str, Any] = {
            "name": "🚀 Deployment 🚀",
            "on": {"push": {"branches": ["master", "main"]}},
            "jobs": jobs,
        }

        # Convert the workflow to YAML
        yaml_string = yaml.dump(workflow, sort_keys=False)

        return yaml_string
