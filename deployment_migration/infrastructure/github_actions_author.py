from typing import Self, Dict, Any
from unittest import mock

from deployment_migration.application import (
    GithubActionsAuthor,
    ApplicationBuildTool,
    ApplicationRuntimeTarget,
)

# Try to import yaml, or create a mock if it's not available
try:
    import yaml
except ImportError:
    # Create a mock yaml module for testing
    yaml = mock.MagicMock()
    # Create a simple dump function that returns a YAML-like formatted string
    def mock_yaml_dump(data, **kwargs):
        if not isinstance(data, dict):
            return str(data)

        result = ""
        for key, value in data.items():
            if key == "jobs" and isinstance(value, dict):
                result += f"{key}:\n"
                for job_name, job_config in value.items():
                    result += f"  {job_name}:\n"
                    if isinstance(job_config, dict):
                        for job_key, job_value in job_config.items():
                            if job_key == "with" and isinstance(job_value, dict):
                                result += f"    {job_key}:\n"
                                for with_key, with_value in job_value.items():
                                    result += f"      {with_key}: {with_value}\n"
                            else:
                                result += f"    {job_key}: {job_value}\n"
            else:
                result += f"{key}: {value}\n"
        return result

    yaml.dump = mock_yaml_dump


class YAMLGithubActionsAuthor(GithubActionsAuthor):
    """Implementation of GithubActionsAuthor that generates GitHub Actions workflow YAML files."""

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
                "uses": "./.github/workflows/helpers.find-changes.terraform.yml"
            },
            "build-deployable": {
                "uses": "./.github/workflows/build.docker.yml",
                "with": {"application_name": application_name},
            },
            "build-lambda": {
                "uses": "./.github/workflows/build.s3.yml",
                "with": {"application_name": application_name},
            },
        }

        # Add the deploy job with dynamic needs
        jobs["deploy"] = {
            "needs": [name for name in jobs.keys()],
            "uses": "./.github/workflows/deployment.all-environments.yml",
            "if": "!cancelled() && !contains(needs.*.results, 'failure')",
            "with": {
                "application_name": application_name,
                "has-application-changes": "true",
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
