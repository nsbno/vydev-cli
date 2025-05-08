import re
from typing import Self, Any, Optional

from deployment_migration.application import Terraform


class RegexTerraformModifier(Terraform):
    """Implementation of TerraformModifyer that uses regex to modify Terraform files."""

    def has_module(self: Self, module_source: str, terraform_config: str = None) -> bool:
        """
        Check if a module with the specified source exists in the Terraform configuration.

        :param module_source: The source of the module to check for
        :param terraform_config: The content of the Terraform file to check. If not provided,
                                the method will try to find the configuration in the current directory.
        :return: True if a module with the specified source exists, False otherwise
        """
        if terraform_config is None:
            # If no terraform_config is provided, try to find it in the current directory
            try:
                import os
                from pathlib import Path

                # Look for main.tf in common terraform directories
                potential_paths = [
                    Path("terraform/template/main.tf"),
                    Path("terraform/modules/template/main.tf"),
                    Path("infrastructure/main.tf"),
                    Path("main.tf"),
                ]

                for path in potential_paths:
                    if os.path.exists(path):
                        with open(path, "r") as f:
                            terraform_config = f.read()
                            break

                if terraform_config is None:
                    # If we still don't have a config, return False
                    return False
            except Exception:
                # If there's any error reading the file, return False
                return False

        # Remove any existing ?ref= parameter from the module source
        base_source = module_source.split("?")[0]

        # Create a pattern to match modules with the specified source
        module_pattern = f'module\\s+"[^"]+"\\s+{{[^}}]*?source\\s+\\=\\s+"({re.escape(base_source)}(?:\\?ref=[^"]*)?)"[^}}]*?}}'

        # Search for the pattern in the terraform config
        matches = re.finditer(module_pattern, terraform_config, re.DOTALL)

        # Return True if any matches are found, False otherwise
        return any(matches)

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
