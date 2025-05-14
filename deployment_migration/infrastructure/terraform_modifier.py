import re
import os
import re
from typing import Self, Any, Optional
from pathlib import Path

from deployment_migration.application import Terraform, NotFoundError


class RegexTerraformModifier(Terraform):
    """Implementation of TerraformModifyer that uses regex to modify Terraform files."""

    def find_account_id(self: Self, folder: str) -> str:
        """
        Find AWS account ID from backend S3 bucket configuration in Terraform files.

        :param folder: The folder path containing Terraform files
        :return: AWS account ID extracted from the bucket name
        """
        folder_path = Path(folder)
        tf_files = folder_path.glob("**/*.tf")

        for tf_file in tf_files:
            with open(tf_file, "r") as f:
                content = f.read()
                # Look for backend configuration with S3 bucket
                bucket_match = re.search(r'bucket\s*=\s*"(\d+)-[^"]*"', content)
                if bucket_match:
                    return bucket_match.group(1)

        raise ValueError(f"Could not find account ID in Terraform files in {folder}")

    def has_module(self: Self, module_source: str, infrastructure_folder: Path) -> bool:
        """
        Check if a module with the specified source exists in the Terraform configuration.

        :param module_source: The source of the module to check for
        :param infrastructure_folder: The folder path containing Terraform files
        :return: True if a module with the specified source exists, False otherwise
        """
        # Remove any existing ?ref= parameter from the module source
        base_source = module_source.split("?")[0]

        # Create a pattern to match modules with the specified source
        module_pattern = rf'source\s*=\s*"({re.escape(base_source)}(?:\?ref=[^"]*)?)"'

        # Read all .tf files from the infrastructure folder
        tf_files = infrastructure_folder.glob("**/*.tf")
        for tf_file in tf_files:
            with open(tf_file, "r") as f:
                content = f.read()
                # Search for the pattern in the terraform config
                if re.search(module_pattern, content, re.MULTILINE):
                    return True

        return False

    def update_module_versions(
        self: Self,
        terraform_config: str,
        target_modules: dict[str, str],
    ) -> str:
        """
        Update the versions of specified modules in a Terraform configuration.

        :param terraform_config: The content of the Terraform file
        :param target_modules: A dictionary where keys are module sources and values are the new versions
        :return: The modified Terraform configuration with updated module versions
        """
        modified_config = terraform_config

        for module_source, new_version in target_modules.items():
            # For testing purposes, use a simpler approach
            # Find modules with the specified source and update the source URL with ?ref=version
            base_source = module_source.split("?")[
                0
            ]  # Remove any existing ?ref= parameter
            module_pattern = f'module\\s+"[^"]+"\\s+{{[^}}]*?source\\s+\\=\\s+"({re.escape(base_source)}(?:\\?ref=[^"]*)?)"[^}}]*?}}'

            for module_match in re.finditer(module_pattern, modified_config, re.DOTALL):
                module_text = module_match.group(0)
                current_source = module_match.group(1)

                # Create the new source with the updated version
                new_source = f"{base_source}?ref={new_version}"

                # Find and replace the source attribute with proper whitespace preserved
                source_pattern = f'(source\\s+\\=\\s+)"{re.escape(current_source)}"'
                updated_module = re.sub(
                    source_pattern, f'\\1"{new_source}"', module_text
                )

                # Replace the module in the config
                modified_config = modified_config.replace(module_text, updated_module)

        return modified_config

    def add_module(
        self: Self,
        terraform_config: str,
        name: str,
        source: str,
        version: str,
        variables: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Add a new module to a Terraform configuration.

        :param terraform_config: The content of the Terraform file
        :param name: The name of the module
        :param source: The source of the module
        :param version: Optional version of the module
        :param variables: Optional dictionary of variables to set in the module
        :return: The modified Terraform configuration with the new module added
        """
        if variables is None:
            variables = {}

        # Start building the module block
        source_with_version = source if not version else f"{source}?ref={version}"
        module_block = f'module "{name}" {{\n  source = "{source_with_version}"'

        for var_name, var_value in variables.items():
            # Handle different types of values
            if isinstance(var_value, str):
                module_block += f'\n  {var_name} = "{var_value}"'
            elif isinstance(var_value, bool):
                module_block += f"\n  {var_name} = {str(var_value).lower()}"
            elif isinstance(var_value, dict):
                raise NotImplementedError(
                    "If you see this, you need to implement dicts in the TF function"
                )
            else:
                module_block += f"\n  {var_name} = {var_value}"

        # Close the module block
        module_block += "\n}\n"

        # Append the new module to the configuration
        return terraform_config + "\n" + module_block

    def get_parameter(
        self, type_: str, parameter: str, module_folder: Path
    ) -> list[str]:
        """
        Find parameter values in Terraform files based on type and parameter name.
        Searches in both resource and data source blocks.

        :param type_: The type of resource/data to search for (e.g., 'aws_ssm_parameter')
        :param parameter: The parameter name to find
        :param module_folder: The folder path containing Terraform files
        :return: List of parameter values found
        """
        tf_files = module_folder.glob("**/*.tf")
        values = []

        for tf_file in tf_files:
            with open(tf_file, "r") as f:
                content = f.read()
                # Pattern for both resource and data blocks
                resource_pattern = f'(?:resource|data)\\s+"{type_}"\\s+"[^"]+"\\s+{{[^}}]*?{parameter}\\s*=\\s*"([^"]*)"[^}}]*}}'
                matches = re.finditer(resource_pattern, content, re.DOTALL)
                values.extend(match.group(1) for match in matches)

        if len(values) == 0:
            raise NotFoundError(
                f"Could not find parameter {parameter} in {module_folder}"
            )

        return values
