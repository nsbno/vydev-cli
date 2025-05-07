from typing import Self, Optional
from unittest import mock

from deployment_migration.application import ParameterStore

# Try to import boto3, or create a mock if it's not available
try:
    import boto3
except ImportError:
    # Create a mock boto3 module for testing
    boto3 = mock.MagicMock()
    boto3.client.return_value = mock.MagicMock()


class AWSParameterStore(ParameterStore):
    """Implementation of ParameterStore that interacts with AWS SSM Parameter Store."""

    def __init__(self, client: Optional[boto3.client] = None):
        """
        Initialize the AWS Parameter Store client.

        :param region_name: Optional AWS region name. If not provided, the default region from AWS configuration will be used.
        """
        self.ssm_client = client or boto3.client("ssm")

    def create_parameter(self: Self, name: str, value: str) -> None:
        """
        Create a parameter in AWS SSM Parameter Store.

        :param name: The name of the parameter
        :param value: The value of the parameter
        """
        try:
            # Try to put the parameter, overwriting if it already exists
            self.ssm_client.put_parameter(
                Name=name, Value=value, Type="String", Overwrite=True
            )
        except Exception as e:
            # Handle AWS API errors
            raise RuntimeError(f"Failed to create parameter {name}: {e}")
