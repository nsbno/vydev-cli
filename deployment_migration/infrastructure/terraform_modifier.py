import re
from typing import Self, Any, Optional
from pathlib import Path

from deployment_migration.application import Terraform, NotFoundError


class RegexTerraformModifier(Terraform):
    """Implementation of TerraformModifyer that uses regex to modify Terraform files."""

    def remove_vydev_artifact_reference(
        self: Self,
        terraform_config: str,
    ) -> str:
        """
        Remove data source blocks that start with "vydev" from Terraform configuration.

        :param terraform_config: The content of the Terraform file
        :return: The modified Terraform configuration with vydev data sources removed
        """
        # Pattern that handles nested braces (like ${var.name})
        # Matches: data "vy_artifact_version" "name" { ... }
        # where { ... } can contain nested braces like ${var.foo}
        vydev_pattern = (
            r'data\s+"vy_artifact_version"\s+"[^"]*"\s+\{(?:[^{}]|\{[^{}]*\})*\}'
        )

        # Remove all matching data blocks
        return re.sub(vydev_pattern, "", terraform_config)

    def add_data_source(
        self: Self,
        terraform_config: str,
        resource: str,
        name: str,
        variables: dict[str, str],
    ) -> str:
        """
        Add a data source block to a Terraform configuration.

        :param terraform_config: The content of the Terraform file
        :param resource: The type of data source to add
        :param name: The name of the data source
        :param variables: Dictionary of variables to set in the data source
        :return: The modified Terraform configuration with the new data source
        """
        # Start building the data source block
        data_block = f'data "{resource}" "{name}" {{\n'

        # Add variables to the block
        for var_name, var_value in variables.items():
            data_block += f'  {var_name} = "{var_value}"\n'

        # Close the data block
        data_block += "}\n"

        # Append the new data source to the configuration
        return terraform_config + "\n" + data_block

    def replace_image_tag_on_ecs_module(
        self: Self,
        terraform_config: str,
        vy_ecs_image_data_source_name: str,
    ) -> str:
        """
        Replace image tag in ECS module configuration with reference to Vy ECS Image Data source.

        :param vy_ecs_image_data_source_name: Name of the Vy ECS Image Data source
        :return: The modified Terraform configuration with updated image tag
        """
        # Pattern that handles nested blocks by using .*? with DOTALL and lookahead
        # to stop at the next top-level Terraform block
        module_pattern = r'module\s+"([^"]+)"\s+\{(.*?)\}(?=\s*(?:module|resource|data|variable|output|locals|provider|\Z))'

        def replace_image(match):
            module_name = match.group(1)
            module_content = match.group(2)

            # Check if this is an ECS service module
            if "github.com/nsbno/terraform-aws-ecs-service" not in module_content:
                return match.group(0)  # Return unchanged if not ECS module

            # Replace image line with reference to ECR repository
            new_variable = (
                f"\n    image = data.vy_ecs_image.{vy_ecs_image_data_source_name}"
            )
            # Find and replace the image line
            # Pattern matches both quoted strings and unquoted references (local.x, var.x, etc.)
            image_pattern = r"\s+image\s*=\s*(?:\"[^\"]*\"|[^\s\n]+)"
            modified_content = re.sub(image_pattern, new_variable, module_content)

            return f'module "{module_name}" {{{modified_content}}}'

        return re.sub(module_pattern, replace_image, terraform_config, flags=re.DOTALL)

    def find_provider(
        self: Self, target_provider: str, terraform_folder: Path
    ) -> Optional[dict[str, Any]]:
        """
        Find a provider configuration in the Terraform files.

        :param target_provider: The name of the provider to find
        :param terraform_folder: The folder path containing Terraform files
        :return: Dictionary with provider details if found, None otherwise
        """
        # Pattern to find the target provider block within required_providers
        # This matches: provider_name = { ... }
        provider_pattern = rf"{target_provider}\s*=\s*{{"

        # Read all .tf files from the terraform folder
        tf_files = terraform_folder.glob("**/*.tf")
        for tf_file in tf_files:
            with open(tf_file, "r") as f:
                content = f.read()
                match = re.search(provider_pattern, content)
                if match:
                    start_pos = match.end() - 1  # Position of opening '{'
                    bracket_count = 0
                    end_pos = -1

                    for i in range(start_pos, len(content)):
                        if content[i] == "{":
                            bracket_count += 1
                        elif content[i] == "}":
                            bracket_count -= 1
                            if bracket_count == 0:
                                end_pos = i
                                break

                    if end_pos == -1:
                        continue  # Couldn't find matching bracket

                    # Extract the provider block content
                    provider_block = content[start_pos + 1 : end_pos]

                    # Extract version from the provider block
                    version_match = re.search(
                        r'version\s*=\s*"([^"]*)"', provider_block
                    )
                    version = version_match.group(1) if version_match else None

                    # Extract source if present
                    source_match = re.search(r'source\s*=\s*"([^"]*)"', provider_block)
                    source = source_match.group(1) if source_match else None

                    return {
                        "name": target_provider,
                        "version": version,
                        "source": source,
                        "file": Path(tf_file),
                    }

        return None

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
        # Pattern to find required_providers block start
        provider_block_start_pattern = r"required_providers\s+{"

        # Check if required_providers block exists
        required_providers_match = re.search(provider_block_start_pattern, modified_config)

        if required_providers_match:
            start_pos = required_providers_match.end() - 1  # Position of opening '{'
            bracket_count = 0
            end_pos = -1

            for i in range(start_pos, len(modified_config)):
                if modified_config[i] == "{":
                    bracket_count += 1
                elif modified_config[i] == "}":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i
                        break

            if end_pos != -1:
                # Extract the full required_providers block including the braces
                block_start = required_providers_match.start()
                full_block = modified_config[block_start : end_pos + 1]
                block_text = full_block

                # Update each provider version within the block
                for provider_name, new_version in target_providers.items():
                    # Match provider configuration and update version
                    # Pattern: provider_name = { ... version = "old_version" ... }
                    # Use non-greedy match with DOTALL to handle nested braces
                    provider_pattern = f'({provider_name}\\s*=\\s*{{.*?version\\s*=\\s*)"[^"]*"'

                    # Update version while preserving formatting
                    updated_block = re.sub(
                        provider_pattern, f'\\1"{new_version}"', block_text, flags=re.DOTALL
                    )

                    block_text = updated_block

                # Replace old block with updated one
                modified_config = modified_config.replace(full_block, block_text)
            else:
                # If we couldn't find the closing brace, fall back to the old behavior
                # (This shouldn't happen with valid Terraform config)
                pass
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
        # Find the module declaration start
        module_start_pattern = rf'module\s+"{re.escape(target_module)}"\s+{{'
        module_start_match = re.search(module_start_pattern, terraform_config)

        if not module_start_match:
            raise NotFoundError(
                f"Could not find module '{target_module}' in the Terraform configuration"
            )

        # Use bracket counting to find the matching closing brace
        start_pos = module_start_match.end() - 1  # Position of opening '{'
        bracket_count = 0
        end_pos = -1

        for i in range(start_pos, len(terraform_config)):
            if terraform_config[i] == "{":
                bracket_count += 1
            elif terraform_config[i] == "}":
                bracket_count -= 1
                if bracket_count == 0:
                    end_pos = i
                    break

        if end_pos == -1:
            raise NotFoundError(
                f"Could not find matching closing brace for module '{target_module}'"
            )

        # Extract module content
        module_start = module_start_match.start()
        module_content = terraform_config[start_pos + 1 : end_pos]

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

        # Build the modified module
        modified_module = (
            terraform_config[module_start : start_pos + 1]
            + module_content
            + var_assignments
            + "\n"
            + terraform_config[end_pos : end_pos + 1]
        )

        # Replace the module in the config
        original_module = terraform_config[module_start : end_pos + 1]
        return terraform_config.replace(original_module, modified_module)

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

            # Found the ECS module, now look for lb_listeners using bracket counting
            lb_listeners_start = re.search(r"lb_listeners\s*=\s*\[", module_content)
            if not lb_listeners_start:
                continue

            # Check if test_listener_arn already exists
            if "test_listener_arn" in module_content:
                continue

            # Find the matching closing bracket for lb_listeners array
            start_pos = lb_listeners_start.end() - 1  # Position of '['
            bracket_count = 0
            end_pos = -1

            for i in range(start_pos, len(module_content)):
                if module_content[i] == "[":
                    bracket_count += 1
                elif module_content[i] == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i
                        break

            if end_pos == -1:
                continue  # Couldn't find matching bracket

            # Extract the full lb_listeners declaration
            lb_listeners_full = module_content[lb_listeners_start.start() : end_pos + 1]

            # Find the first '{' inside the array to insert test_listener_arn after it
            first_brace = lb_listeners_full.find("{")
            if first_brace == -1:
                continue

            # Add test_listener_arn after the opening brace
            test_listener_value = (
                f"module.{metadata_module_name}.load_balancer.https_test_listener_arn"
            )
            test_listener_line = f"\n      test_listener_arn = {test_listener_value}\n"

            modified_lb_listeners = (
                lb_listeners_full[: first_brace + 1]
                + test_listener_line
                + lb_listeners_full[first_brace + 1 :]
            )

            # Replace in module content
            modified_module_content = module_content.replace(
                lb_listeners_full, modified_lb_listeners
            )

            # Replace the module in the config
            original_module = module_match.group(0)
            modified_module = f'module "{module_name}" {{{modified_module_content}}}'

            return terraform_config.replace(original_module, modified_module)

        # If we didn't find the module or lb_listeners, return the original config
        return terraform_config

    def add_force_new_deployment_to_ecs_module(
        self: Self, terraform_config: str
    ) -> str:
        """
        Add force_new_deployment = true to the ECS module configuration.

        This ensures that ECS tasks are redeployed when the Terraform configuration changes.

        :param terraform_config: The content of the Terraform file
        :return: The modified Terraform configuration with force_new_deployment added
        """
        # Find the ECS module in the config to get its name
        target_module_source = "github.com/nsbno/terraform-aws-ecs-service"

        # Find all module declarations using regex
        module_start_pattern = r'module\s+"([^"]+)"\s+\{'

        for module_match in re.finditer(module_start_pattern, terraform_config):
            module_name = module_match.group(1)
            start_pos = module_match.end() - 1  # Position of opening '{'

            # Use bracket counting to find the matching closing brace
            bracket_count = 0
            end_pos = -1

            for i in range(start_pos, len(terraform_config)):
                if terraform_config[i] == "{":
                    bracket_count += 1
                elif terraform_config[i] == "}":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i
                        break

            if end_pos == -1:
                continue  # Couldn't find matching bracket

            # Extract module content
            module_content = terraform_config[start_pos + 1 : end_pos]

            # Check if this is the ECS module
            source_match = re.search(
                rf'source\s*=\s*"{re.escape(target_module_source)}(?:\?ref=[^"]*)?',
                module_content,
            )
            if not source_match:
                continue

            # Check if force_new_deployment already exists
            if "force_new_deployment" in module_content:
                return terraform_config

            # Use add_variable to add force_new_deployment = true
            return self.add_variable(
                terraform_config, module_name, {"force_new_deployment": True}
            )

        # If we didn't find the ECS module, raise an error
        raise NotFoundError("No ECS module was found in the configuration.")

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
            if ".terraform" in str(tf_file):
                continue
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

    def update_spring_boot_service_module(
        self, terraform_config: str, ecr_data_source_name: str
    ) -> str:
        """Update Spring Boot service module for RC3 compatibility.

        Removes docker_image and datadog_tags variables, and adds repository_url.

        Args:
            terraform_config: The Terraform configuration string
            ecr_data_source_name: Name of the ECR data source (e.g., 'ecr_repository')

        Returns:
            Updated Terraform configuration string
        """
        # Find all module declarations using bracket counting
        module_start_pattern = r'module\s+"([^"]+)"\s+\{'

        for module_match in re.finditer(module_start_pattern, terraform_config):
            start_pos = module_match.end() - 1  # Position of opening '{'

            # Use bracket counting to find the matching closing brace
            bracket_count = 0
            end_pos = -1

            for i in range(start_pos, len(terraform_config)):
                if terraform_config[i] == "{":
                    bracket_count += 1
                elif terraform_config[i] == "}":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = i
                        break

            if end_pos == -1:
                continue  # Couldn't find matching bracket

            # Extract the full module block
            module_block = terraform_config[module_match.start() : end_pos + 1]

            # Check if this is a Spring Boot service module
            if "spring-boot-service" not in module_block:
                continue

            # Found the Spring Boot module, now update it
            updated_module = module_block

            # Remove docker_image line (including leading whitespace)
            docker_image_pattern = r"^[ \t]*docker_image\s*=\s*[^\n]+\n"
            updated_module = re.sub(
                docker_image_pattern, "", updated_module, flags=re.MULTILINE
            )

            # Remove datadog_tags block (handles multi-line block with nested braces)
            # Use bracket counting for datadog_tags
            datadog_match = re.search(r"datadog_tags\s*=\s*\{", updated_module)
            if datadog_match:
                datadog_start = datadog_match.start()
                brace_start = datadog_match.end() - 1
                bracket_count = 0
                datadog_end = -1

                for i in range(brace_start, len(updated_module)):
                    if updated_module[i] == "{":
                        bracket_count += 1
                    elif updated_module[i] == "}":
                        bracket_count -= 1
                        if bracket_count == 0:
                            datadog_end = i + 1
                            break

                if datadog_end > 0:
                    # Find the newline after the closing brace if it exists
                    if (
                        datadog_end < len(updated_module)
                        and updated_module[datadog_end] == "\n"
                    ):
                        datadog_end += 1
                    # Remove the entire datadog_tags block including leading whitespace
                    line_start = datadog_start
                    while line_start > 0 and updated_module[line_start - 1] in " \t":
                        line_start -= 1
                    updated_module = (
                        updated_module[:line_start] + updated_module[datadog_end:]
                    )

            # Add repository_url if not already present
            if "repository_url" not in updated_module:
                # Find the last closing brace of the module and add repository_url before it
                last_brace = updated_module.rfind("}")
                if last_brace > 0:
                    repository_url_line = f"  repository_url = data.aws_ecr_repository.{ecr_data_source_name}.repository_url\n"
                    updated_module = (
                        updated_module[:last_brace]
                        + repository_url_line
                        + updated_module[last_brace:]
                    )

            # Replace the old module block with the updated one
            terraform_config = terraform_config.replace(module_block, updated_module)

            # We only process the first Spring Boot module found
            return terraform_config

        # No Spring Boot module found, return config unchanged
        return terraform_config
