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
        application_name: str,
        build_tool: ApplicationBuildTool,
        runtime_target: ApplicationRuntimeTarget,
        add_tests: bool = True,
    ) -> dict[str, Any]:
        if build_tool == ApplicationBuildTool.GRADLE:
            build_step = {
                "build": {
                    "uses": self._workflow("build", "gradle", "main"),
                    "secrets": "inherit",
                }
            }
        else:
            raise NotImplementedError(f"{build_tool} is currently not supported")

        test_step = {}
        if add_tests:
            test_step = {
                "test": {
                    "needs": ["build"],
                    "uses": self._workflow("test", "gradle", "main"),
                    "secrets": "inherit",
                    "with": {
                        "artifact_name": "${{ needs.build.outputs.artifact_name }}",
                        "artifact_path": "${{ needs.build.outputs.artifact_path }}",
                    },
                }
            }

        if runtime_target == ApplicationRuntimeTarget.ECS:
            package_step = {
                "package": {
                    "uses": self._workflow("pacakge", "docker", "main"),
                    "needs": ["build", *(["test"] if add_tests else [])],
                    "secrets": "inherit",
                    "with": {
                        "application_name": application_name,
                        "artifact_name": "${{ needs.build.outputs.artifact_name }}",
                        "artifact_path": "${{ needs.build.outputs.artifact_path }}",
                    },
                }
            }
        elif runtime_target == ApplicationRuntimeTarget.LAMBDA:
            package_step = {
                "package": {
                    "needs": ["build", *(["test"] if add_tests else [])],
                    "uses": self._workflow("pacakge", "s3", "main"),
                    "secrets": "inherit",
                    "with": {
                        "application_name": application_name,
                        "artifact_name": "${{ needs.build.outputs.artifact_name }}",
                        "artifact_path": "${{ needs.build.outputs.artifact_path }}",
                        "directory_to_zip": "${{ needs.build.outputs.artifact_path }}",
                    },
                }
            }
        else:
            raise NotImplementedError(f"{runtime_target} is currently not supported")

        return {**build_step, **test_step, **package_step}

    def create_deployment_workflow(
        self: Self,
        application_name: str,
        application_build_tool: ApplicationBuildTool,
        application_runtime_target: ApplicationRuntimeTarget,
        terraform_base_folder: str,
    ) -> str:
        """
        Create a GitHub Actions deployment workflow for the application.

        :param application_name: The name of the application
        :param application_build_tool: The build tool used by the application (PYTHON or GRADLE)
        :param application_runtime_target: The runtime target for the application (LAMBDA or ECS)
        :param terraform_base_folder: The base folder for Terraform configuration
        :return: The GitHub Actions workflow as a YAML string
        """
        jobs = {
            "terraform-changes": {
                "uses": self._workflow("helpers.find-changes", "terraform", "main"),
                "secrets": "inherit",
            },
            **self._build_and_package(
                application_name, application_build_tool, application_runtime_target
            ),
        }

        # Add the deploy job with dynamic needs
        jobs["deploy"] = {
            "needs": [name for name in jobs.keys()],
            "uses": self._workflow("deployment", "all-environments", "main"),
            "secrets": "inherit",
            "if": "!cancelled() && !contains(needs.*.results, 'failure')",
            "with": {
                "application_name": application_name,
                "terraform-changes": f"${{{{ needs.terraform-changes.outputs.has-changes }}}}",
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
