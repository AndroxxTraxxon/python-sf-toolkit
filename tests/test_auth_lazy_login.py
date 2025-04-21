import pytest
from unittest.mock import patch

from sf_toolkit.auth.login_lazy import lazy_login
from sf_toolkit.auth.types import LazyParametersMissing


@patch('sf_toolkit.auth.login_lazy.cli_login')
def test_lazy_login_cli(mock_cli_login):
    """Test lazy_login with CLI parameters."""
    # Setup mock
    mock_cli_login.return_value = "mock_cli_login_function"

    # Call with CLI parameters
    result = lazy_login(sf_cli_alias="my-dev-org")

    # Verify the correct login method was called
    mock_cli_login.assert_called_once_with("my-dev-org", None)
    assert result == "mock_cli_login_function"


@patch('sf_toolkit.auth.login_lazy.cli_login')
def test_lazy_login_cli_with_exec_path(mock_cli_login):
    """Test lazy_login with CLI parameters including exec path."""
    # Setup mock
    mock_cli_login.return_value = "mock_cli_login_function"

    # Call with CLI parameters including exec path
    result = lazy_login(sf_cli_alias="my-dev-org", sf_cli_exec_path="/path/to/sf")

    # Verify the correct login method was called with both parameters
    mock_cli_login.assert_called_once_with("my-dev-org", "/path/to/sf")
    assert result == "mock_cli_login_function"


@patch('sf_toolkit.auth.login_lazy.lazy_oauth_login')
def test_lazy_login_oauth_jwt(mock_oauth_login):
    """Test lazy_login with OAuth JWT parameters."""
    # Setup mock
    mock_oauth_login.return_value = "mock_oauth_jwt_function"

    # Call with parameters for JWT bearer flow
    result = lazy_login(
        username="test@example.com",
        consumer_key="test_consumer_key",
        private_key="test_private_key"
    )

    # Verify the correct login method was called
    mock_oauth_login.assert_called_once()
    kwargs = mock_oauth_login.call_args[1]
    assert kwargs["username"] == "test@example.com"
    assert kwargs["consumer_key"] == "test_consumer_key"
    assert kwargs["private_key"] == "test_private_key"
    assert result == "mock_oauth_jwt_function"


@patch('sf_toolkit.auth.login_lazy.lazy_oauth_login')
def test_lazy_login_oauth_password(mock_oauth_login):
    """Test lazy_login with OAuth username-password parameters."""
    # Setup mock
    mock_oauth_login.return_value = "mock_oauth_password_function"

    # Call with parameters for password flow
    result = lazy_login(
        username="test@example.com",
        password="test_password",
        consumer_key="test_consumer_key",
        consumer_secret="test_consumer_secret"
    )

    # Verify the correct login method was called
    mock_oauth_login.assert_called_once()
    kwargs = mock_oauth_login.call_args[1]
    assert kwargs["username"] == "test@example.com"
    assert kwargs["password"] == "test_password"
    assert kwargs["consumer_key"] == "test_consumer_key"
    assert kwargs["consumer_secret"] == "test_consumer_secret"
    assert result == "mock_oauth_password_function"


@patch('sf_toolkit.auth.login_lazy.lazy_oauth_login')
def test_lazy_login_oauth_client_credentials(mock_oauth_login):
    """Test lazy_login with OAuth client credentials parameters."""
    # Setup mock
    mock_oauth_login.return_value = "mock_oauth_client_credentials_function"

    # Call with parameters for client credentials flow
    result = lazy_login(
        consumer_key="test_consumer_key",
        consumer_secret="test_consumer_secret"
    )

    # Verify the correct login method was called
    mock_oauth_login.assert_called_once()
    kwargs = mock_oauth_login.call_args[1]
    assert kwargs["consumer_key"] == "test_consumer_key"
    assert kwargs["consumer_secret"] == "test_consumer_secret"
    assert "username" not in kwargs
    assert "password" not in kwargs
    assert result == "mock_oauth_client_credentials_function"


@patch('sf_toolkit.auth.login_lazy.lazy_soap_login')
def test_lazy_login_soap_security_token(mock_soap_login):
    """Test lazy_login with SOAP security token parameters."""
    # Setup mock
    mock_soap_login.return_value = "mock_soap_security_token_function"

    # Call with parameters for security token login
    result = lazy_login(
        username="test@example.com",
        password="test_password",
        security_token="test_security_token"
    )

    # Verify the correct login method was called
    mock_soap_login.assert_called_once()
    kwargs = mock_soap_login.call_args[1]
    assert kwargs["username"] == "test@example.com"
    assert kwargs["password"] == "test_password"
    assert kwargs["security_token"] == "test_security_token"
    assert result == "mock_soap_security_token_function"


@patch('sf_toolkit.auth.login_lazy.lazy_soap_login')
def test_lazy_login_soap_ip_filtering(mock_soap_login):
    """Test lazy_login with SOAP IP filtering parameters."""
    # Setup mock
    mock_soap_login.return_value = "mock_soap_ip_filtering_function"

    # Call with parameters for IP filtering login
    result = lazy_login(
        username="test@example.com",
        password="test_password",
        domain="test"
    )

    # Verify the correct login method was called
    mock_soap_login.assert_called_once()
    kwargs = mock_soap_login.call_args[1]
    assert kwargs["username"] == "test@example.com"
    assert kwargs["password"] == "test_password"
    assert kwargs["domain"] == "test"
    assert result == "mock_soap_ip_filtering_function"


@patch('sf_toolkit.auth.login_lazy.lazy_soap_login')
def test_lazy_login_soap_organization_id(mock_soap_login):
    """Test lazy_login with SOAP organization ID parameters."""
    # Setup mock
    mock_soap_login.return_value = "mock_soap_org_id_function"

    # Call with parameters for organization ID login
    result = lazy_login(
        username="test@example.com",
        password="test_password",
        organizationId="00D000000000001"
    )

    # Verify the correct login method was called
    mock_soap_login.assert_called_once()
    kwargs = mock_soap_login.call_args[1]
    assert kwargs["username"] == "test@example.com"
    assert kwargs["password"] == "test_password"
    assert kwargs["organizationId"] == "00D000000000001"
    assert result == "mock_soap_org_id_function"


def test_lazy_login_invalid_parameters():
    """Test lazy_login with invalid parameters."""
    # Call with invalid parameters (missing all required params)
    with pytest.raises(LazyParametersMissing, match="Could not determine authentication method"):
        lazy_login(domain="test")

    # Call with incomplete OAuth parameters (missing consumer_secret or private_key)
    with pytest.raises(LazyParametersMissing, match="Unable to determine authentication method"):
        lazy_login(username="test@example.com", consumer_key="test_key")


@patch('sf_toolkit.auth.login_lazy.cli_login')
@patch('sf_toolkit.auth.login_lazy.lazy_oauth_login')
@patch('sf_toolkit.auth.login_lazy.lazy_soap_login')
def test_lazy_login_priority(mock_soap_login, mock_oauth_login, mock_cli_login):
    """Test that lazy_login prioritizes methods correctly."""
    # Setup mocks
    mock_cli_login.return_value = "mock_cli_login_function"
    mock_oauth_login.return_value = "mock_oauth_login_function"
    mock_soap_login.return_value = "mock_soap_login_function"

    # 1. CLI should take precedence over everything else
    result = lazy_login(
        sf_cli_alias="my-dev-org",
        username="test@example.com",
        password="test_password",
        consumer_key="test_key"
    )

    # Verify CLI login was used
    mock_cli_login.assert_called_once()
    mock_oauth_login.assert_not_called()
    mock_soap_login.assert_not_called()
    assert result == "mock_cli_login_function"

    # Reset mocks
    mock_cli_login.reset_mock()
    mock_oauth_login.reset_mock()
    mock_soap_login.reset_mock()

    # 2. OAuth should take precedence over SOAP
    result = lazy_login(
        username="test@example.com",
        password="test_password",
        consumer_key="test_key",
        consumer_secret="test_secret"
    )

    # Verify OAuth login was used
    mock_cli_login.assert_not_called()
    mock_oauth_login.assert_called_once()
    mock_soap_login.assert_not_called()
    assert result == "mock_oauth_login_function"
