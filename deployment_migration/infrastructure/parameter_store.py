from typing import Self, Optional
import configparser
import os.path

from deployment_migration.application import AWS

import boto3


class AWSAWS(AWS):
    """Implementation of ParameterStore that interacts with AWS SSM Parameter Store."""

    def __init__(self: Self, client: Optional["boto3.client"] = None):
        """
        Initialize the AWS Parameter Store client.

        :param region_name: Optional AWS region name. If not provided, the default region from AWS configuration will be used.
        """
        self.ssm_client = client

    def create_parameter(
        self: Self, name: str, value: str, profile_name: Optional[str] = None
    ) -> None:
        """
        Create a parameter in AWS SSM Parameter Store.

        :param name: The name of the parameter
        :param value: The value of the parameter
        """
        client = self.ssm_client
        if not client:
            session = boto3.Session(profile_name=profile_name, region_name="eu-west-1")
            self.ssm_client = session.client("ssm")

        try:
            # Try to put the parameter, overwriting if it already exists
            self.ssm_client.put_parameter(
                Name=name, Value=value, Type="String", Overwrite=True
            )
        except Exception as e:
            # Handle AWS API errors
            raise RuntimeError(f"Failed to create parameter {name}: {e}")

    def find_aws_profile_names(self: Self, account_id: str) -> list[str]:
        """
        Find AWS profile names in config file that contain the specified account ID.

        :param account_id: AWS account ID to search for
        :return: List of profile names containing the account ID
        """
        config = configparser.ConfigParser()
        config_path = os.path.expanduser("~/.aws/config")

        if not os.path.exists(config_path):
            return []

        config.read(config_path)
        matching_profiles = []

        possible_account_id_locations = [
            "role_arn",
            "credential_process",
            "granted_sso_account_id",
        ]

        for section in config.sections():
            if not section.startswith("profile "):
                continue

            profile_name = section.replace("profile ", "")

            if not any(
                account_id not in config[section].get(location, "")
                for location in possible_account_id_locations
            ):
                continue

            matching_profiles.append(profile_name)

        return matching_profiles
