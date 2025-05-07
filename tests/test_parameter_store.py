import pytest
from unittest import mock

from deployment_migration.infrastructure.parameter_store import AWSParameterStore


# Mock ClientError exception
class MockClientError(Exception):
    def __init__(self, error_response, operation_name):
        self.response = error_response
        self.operation_name = operation_name
        super().__init__(f"{operation_name} error: {error_response}")


# Use MockClientError instead of botocore.exceptions.ClientError


@pytest.fixture
def mock_ssm_client():
    """Create a mock SSM client."""
    # Create a mock SSM client directly without using boto3
    mock_ssm = mock.Mock()
    yield mock_ssm


@pytest.fixture
def parameter_store(mock_ssm_client) -> AWSParameterStore:
    """Create an AWSParameterStore instance with a mocked SSM client."""
    return AWSParameterStore(mock_ssm_client)


def test_create_parameter_calls_put_parameter(parameter_store, mock_ssm_client):
    """Test that create_parameter calls put_parameter with the correct arguments."""
    parameter_name = "/__platform__/versions/test-app"
    parameter_value = "latest"

    parameter_store.create_parameter(parameter_name, parameter_value)

    mock_ssm_client.put_parameter.assert_called_once_with(
        Name=parameter_name, Value=parameter_value, Type="String", Overwrite=True
    )


def test_create_parameter_handles_aws_api_error(parameter_store, mock_ssm_client):
    """Test that create_parameter handles AWS API errors correctly."""
    # Arrange
    parameter_name = "/__platform__/versions/test-app"
    parameter_value = "latest"

    error_response = {
        "Error": {"Code": "InternalServerError", "Message": "Internal server error"}
    }
    mock_ssm_client.put_parameter.side_effect = MockClientError(
        error_response, "PutParameter"
    )

    with pytest.raises(RuntimeError) as excinfo:
        parameter_store.create_parameter(parameter_name, parameter_value)

    assert parameter_name in str(excinfo.value)


def test_create_parameter_with_empty_name_raises_error(
    parameter_store, mock_ssm_client
):
    """Test that create_parameter raises an error when the parameter name is empty."""
    # Arrange
    parameter_name = ""
    parameter_value = "latest"

    error_response = {
        "Error": {
            "Code": "ValidationException",
            "Message": "Parameter name is required",
        }
    }
    mock_ssm_client.put_parameter.side_effect = MockClientError(
        error_response, "PutParameter"
    )

    with pytest.raises(RuntimeError) as excinfo:
        parameter_store.create_parameter(parameter_name, parameter_value)

    assert parameter_name in str(excinfo.value)


def test_create_parameter_with_empty_value(parameter_store, mock_ssm_client):
    """Test that create_parameter works with an empty parameter value."""
    # Arrange
    parameter_name = "/__platform__/versions/test-app"
    parameter_value = ""

    parameter_store.create_parameter(parameter_name, parameter_value)

    mock_ssm_client.put_parameter.assert_called_once_with(
        Name=parameter_name, Value=parameter_value, Type="String", Overwrite=True
    )
