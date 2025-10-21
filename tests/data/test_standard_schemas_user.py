import pytest

from sf_toolkit.client import SalesforceClient
from sf_toolkit.data.standard_schemas import User


def test_user_password_expired(mocker):
    # Setup mock client and response
    mock_client = mocker.Mock()
    mock_client.sobjects_url = (
        "https://example.salesforce.com/services/data/v50.0/sobjects"
    )
    # Mock the connection factory
    mocker.patch(
        "sf_toolkit.data.standard_schemas.SalesforceClient.get_connection",
        return_value=mock_client,
    )
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"IsExpired": True}
    mock_client.get.return_value = mock_response

    # Create user and test password_expired method
    user = User(Id="001XXXXXXXXXXXX")

    assert user.password_expired() is True
    mock_client.get.assert_called_once_with(
        f"{mock_client.sobjects_url}/User/{user.Id}/password",
        headers={"Accept": "application/json"},
    )


def test_user_set_password(mocker):
    # Setup mock client
    mock_client = mocker.Mock()
    mock_client.sobjects_url = (
        "https://example.salesforce.com/services/data/v50.0/sobjects"
    )
    # Mock the connection factory
    mocker.patch(
        "sf_toolkit.data.standard_schemas.SalesforceClient.get_connection",
        return_value=mock_client,
    )

    # Create user and test set_password method
    user = User(Id="001XXXXXXXXXXXX")

    user.set_password("NewSecurePassword123!")

    mock_client.post.assert_called_once_with(
        f"{mock_client.sobjects_url}/User/{user.Id}/password",
        json={"NewPassword": "NewSecurePassword123!"},
    )


def test_user_reset_password(mocker):
    # Setup mock client and response
    mock_client = mocker.Mock()
    mock_client.sobjects_url = (
        "https://example.salesforce.com/services/data/v50.0/sobjects"
    )
    # Mock the connection factory
    mocker.patch(
        "sf_toolkit.data.standard_schemas.SalesforceClient.get_connection",
        return_value=mock_client,
    )
    mock_response = mocker.Mock()
    mock_new_password = "Auto-Generated-Password-123"
    mock_response.json.return_value = {"NewPassword": mock_new_password}
    mock_client.delete.return_value = mock_response

    # Create user and test reset_password method
    user = User(Id="001XXXXXXXXXXXX")

    new_password = user.reset_password()

    assert new_password == mock_new_password
    mock_client.delete.assert_called_once_with(
        f"{mock_client.sobjects_url}/User/{user.Id}/password",
        headers={"Accept": "application/json"},
    )


def test_password_operations_with_connection_string(mocker):
    # Setup mock client factory and client
    mock_client = mocker.Mock()
    mock_client.sobjects_url = (
        "https://example.salesforce.com/services/data/v50.0/sobjects"
    )

    # Mock the connection factory
    mocker.patch(
        "sf_toolkit.data.standard_schemas.SalesforceClient.get_connection",
        return_value=mock_client,
    )
    # Test with connection string
    user = User(Id="001XXXXXXXXXXXX")

    # For password_expired
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"IsExpired": False}
    mock_client.get.return_value = mock_response

    assert user.password_expired(connection="test_connection") is False

    new_password = "TestPassword456"

    # For set_password
    user.set_password(new_password, connection="test_connection")

    mock_client.post.assert_called_once_with(
        f"{mock_client.sobjects_url}/User/{user.Id}/password",
        json={"NewPassword": new_password},
    )

    # For reset_password
    reset_password = "Reset-Password-789"
    reset_response = mocker.Mock()
    reset_response.json.return_value = {"NewPassword": reset_password}
    mock_client.delete.return_value = reset_response

    assert user.reset_password(connection="test_connection") == reset_password


def test_password_operations_without_id(mocker):
    # Create user without ID
    user = User()
    mock_client = mocker.Mock()
    # Mock the connection factory
    mocker.patch(
        "sf_toolkit.data.standard_schemas.SalesforceClient.get_connection",
        return_value=mock_client,
    )

    # All operations should raise AssertionError when ID is not set
    with pytest.raises(
        AssertionError, match="User Id must be set to check password expiration"
    ):
        user.password_expired()

    with pytest.raises(AssertionError, match="User Id must be set to set password"):
        user.set_password("SomePassword")

    with pytest.raises(AssertionError, match="User Id must be set to set password"):
        user.reset_password()
