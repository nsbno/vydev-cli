import re
from typing import Self, Any, Optional
from pathlib import Path

from deployment_migration.application import Terraform, NotFoundError


class RegexTerraformModifier(Terraform):
    """Implementation of TerraformModifyer that uses regex to modify Terraform files."""

    def find_provider(
        self: Self, module_source: str, terraform_folder: Path
    ) -> Optional[dict[str, Any]]:
        raise NotImplementedError("Not implemented yet")

    def update_provider_versions(
        self: Self,
        terraform_config: str,
        target_providers: dict[str, str],
    ) -> str:
        """
        Update the versions of specified providers in a Terraform configuration.

        :param terraform_config: The content of the Terraform file
        :param target_providers: A dictionary where keys are provider names and values are the new versions
        :return: The modified Terraform configuration with updated provider versions
        """
        modified_config = terraform_config
        # Create pattern to match required_providers blocks
        provider_block_pattern = r"required_providers\s+{[^}]*}"

        # Check if required_providers block exists
        required_providers_block = re.search(provider_block_pattern, modified_config)

        if required_providers_block:
            # If block exists, update provider versions within it
            block_text = required_providers_block.group(0)
            for provider_name, new_version in target_providers.items():
                # Match provider configuration within required_providers block
                provider_pattern = f'({provider_name}\\s*=\\s*{{[^}}]*version\\s*=\\s*)"[^"]*"([^}}]*}})'

                # Update version while preserving formatting
                updated_block = re.sub(
                    provider_pattern, f'\\1"{new_version}"\\2', block_text
                )

                block_text = updated_block

            # Replace old block with updated one
            modified_config = modified_config.replace(
                required_providers_block.group(0), block_text
            )
        else:
            # If no required_providers block exists, create one
            providers_text = "terraform {\n  required_providers {\n"
            for provider_name, version in target_providers.items():
                providers_text += (
                    f'    {provider_name} = {{\n      version = "{version}"\n    }}\n'
                )
            providers_text += "  }\n}\n"

            modified_config = providers_text + modified_config

        return modified_config

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
                if not (
                    var_value.startswith("module.") or var_value.startswith("var.")
                ):
                    # If the value doesn't start with "module." or "var.", wrap it in quotes
                    var_value = f'"{var_value}"'

                module_block += f"\n  {var_name} = {var_value}"
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

    def find_module(
        self: Self, module_source: str, infrastructure_folder: Path
    ) -> Optional[dict[str, Any]]:
        """
        Find a module with the specified source in the Terraform configuration and return its details.

        :param module_source: The source of the module to find
        :param infrastructure_folder: The folder path containing Terraform files
        :return: Dictionary with module details if found, None otherwise
        """
        # Remove any existing ?ref= parameter from the module source
        base_source = module_source.split("?")[0]

        # Create a pattern to match modules with the specified source and capture module details
        module_pattern = rf'module\s+"([^"]+)"\s+{{\s*([^}}]*?source\s*=\s*"({re.escape(base_source)}(?:\?ref=([^"]*))?)"[^}}]*?)}}'

        # Read all .tf files from the infrastructure folder
        tf_files = infrastructure_folder.glob("**/*.tf")
        for tf_file in tf_files:
            with open(tf_file, "r") as f:
                content = f.read()
                # Search for the pattern in the terraform config
                for match in re.finditer(module_pattern, content, re.DOTALL):
                    module_name = match.group(1)
                    module_block = match.group(2)
                    module_source_value = match.group(3)
                    module_version = match.group(4) if match.group(4) else None

                    # Extract variables from the module block
                    variables = {}
                    var_pattern = r'(\w+)\s*=\s*(?:"([^"]*)"|(\w+))'
                    for var_match in re.finditer(var_pattern, module_block):
                        var_name = var_match.group(1)
                        if var_name == "source":  # Skip the source attribute
                            continue
                        var_value = (
                            var_match.group(2)
                            if var_match.group(2) is not None
                            else var_match.group(3)
                        )
                        variables[var_name] = var_value

                    return {
                        "name": module_name,
                        "source": module_source_value,
                        "version": module_version,
                        "variables": variables,
                        "file_path": Path(tf_file),
                    }

        return None

    def add_variable(
        self: Self, terraform_config: str, target_module: str, variables: dict[str, Any]
    ) -> str:
        """
        Add variables to an existing module in a Terraform configuration.

        :param terraform_config: The content of the Terraform file
        :param target_module: The name of the module to add variables to
        :param variables: Dictionary of variables to add to the module
        :return: The modified Terraform configuration with added variables
        """
        # Create a pattern to match the target module
        # Use a more flexible pattern that handles different whitespace and indentation
        module_pattern = rf'(module\s+"{re.escape(target_module)}"\s+{{[^}}]*?)(\s*}})'

        # Find the module in the config
        module_match = re.search(module_pattern, terraform_config, re.DOTALL)
        if not module_match:
            raise NotFoundError(
                f"Could not find module '{target_module}' in the Terraform configuration"
            )

        module_content = module_match.group(1)
        module_end = module_match.group(2)

        # Build the variable assignments
        var_assignments = ""
        for var_name, var_value in variables.items():
            # Handle different types of values
            if isinstance(var_value, str):
                var_assignments += f'\n  {var_name} = "{var_value}"'
            elif isinstance(var_value, bool):
                var_assignments += f"\n  {var_name} = {str(var_value).lower()}"
            elif isinstance(var_value, dict):
                raise NotImplementedError(
                    "If you see this, you need to implement dicts in the TF function"
                )
            else:
                var_assignments += f"\n  {var_name} = {var_value}"

        # Insert the variables before the closing brace
        modified_module = module_content + var_assignments + module_end

        # Replace the module in the config
        return terraform_config.replace(module_match.group(0), modified_module)

    def add_test_listener_to_ecs_module(
        self: Self, terraform_config: str, metadata_module_name: str
    ) -> str:
        """
        Add test_listener_arn to the lb_listeners array in the ECS module configuration.

        This is a specific implementation for handling the test listener case.

        :param terraform_config: The content of the Terraform file
        :param metadata_module_name: The name of the metadata module to reference
        :return: The modified Terraform configuration with added test_listener_arn to lb_listeners
        """
        # Find the ECS module in the config
        target_module_name = "github.com/nsbno/terraform-aws-ecs-service"
        module_pattern = (
            r'module\s+"([^"]+)"\s+{(.*?)}(?=\s*(?:module|resource|data|provider|\Z))'
        )

        for module_match in re.finditer(module_pattern, terraform_config, re.DOTALL):
            module_name = module_match.group(1)
            module_content = module_match.group(2)

            # Check if this is the ECS module
            source_match = re.search(
                rf'source\s*=\s*"{re.escape(target_module_name)}(?:\?ref=[^"]*)?',
                module_content,
            )
            if not source_match:
                continue

            # Found the ECS module, now look for lb_listeners
            lb_listeners_match = re.search(
                r"lb_listeners\s*=\s*\[\s*{(.*?)}\s*\]", module_content, re.DOTALL
            )
            if not lb_listeners_match:
                continue

            # Found lb_listeners, check if test_listener_arn already exists
            lb_listeners_content = lb_listeners_match.group(1)
            if "test_listener_arn" in lb_listeners_content:
                continue

            # Add test_listener_arn to the lb_listeners
            test_listener_value = (
                f"module.{metadata_module_name}.load_balancer.https_test_listener_arn"
            )
            # Insert test_listener_arn at the beginning of the lb_listeners content
            modified_lb_listeners_content = f"\n    test_listener_arn = {test_listener_value}\n{lb_listeners_content}"

            # Replace the lb_listeners content in the module
            # Make sure to include the closing brackets }] at the end
            full_lb_listeners = f"lb_listeners = [{{{lb_listeners_content}}}]"
            modified_full_lb_listeners = (
                f"lb_listeners = [{{{modified_lb_listeners_content}}}]"
            )
            modified_module_content = module_content.replace(
                full_lb_listeners, modified_full_lb_listeners
            )

            # Replace the module content in the config
            original_module = module_match.group(0)
            modified_module = f'module "{module_name}" {{{modified_module_content}}}'

            return terraform_config.replace(original_module, modified_module)

        # If we didn't find the module or lb_listeners, return the original config
        return terraform_config

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
