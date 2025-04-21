from json import JSONDecodeError
import pytest
import httpx
from unittest.mock import patch, Mock
import base64
import time

from sf_toolkit.auth.login_oauth import (
    token_login,
    password_login,
    client_credentials_flow_login,
    public_key_auth_login,
    lazy_oauth_login
)
from sf_toolkit.auth.types import AuthMissingResponse, LazyParametersMissing, SalesforceToken
from sf_toolkit.exceptions import SalesforceAuthenticationFailed


def test_token_login_success():
    """Test successful token login flow."""
    # Create mock response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "00D...FAKE_TOKEN",
        "instance_url": "https://test.my.salesforce.com",
        "id": "https://login.salesforce.com/id/00D000000000001AAA/005000000000001AAA",
        "token_type": "Bearer",
        "issued_at": "1613412345123",
        "signature": "SIGNATURE"
    }

    # Create and start the generator
    token_gen = token_login(
        "test",
        {"grant_type": "password", "username": "user@example.com"},
        "test_consumer_key"
    )

    # First yield should be a request
    request = next(token_gen)
    assert isinstance(request, httpx.Request)
    assert request.method == "POST"
    assert request.url == "https://test.salesforce.com/services/oauth2/token"

    # Send the mock response
    token = None
    try:
        token_gen.send(mock_response)
    except StopIteration as e:
        token = e.value

    # Verify the returned token
    assert isinstance(token, SalesforceToken)
    assert token.token == "00D...FAKE_TOKEN"
    assert token.instance.host == "test.my.salesforce.com"


def test_token_login_error():
    """Test token login with error response."""
    # Create mock error response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "authentication failure"
    }

    # Create and start the generator
    token_gen = token_login(
        "test",
        {"grant_type": "password", "username": "user@example.com"},
        "test_consumer_key"
    )

    # First yield should be a request
    next(token_gen)  # We don't need the request object here

    # Send the mock error response and expect an exception
    with pytest.raises(SalesforceAuthenticationFailed) as excinfo:
        token_gen.send(mock_response)

    # Verify exception details
    exception = excinfo.value
    assert exception.code == "invalid_grant"
    assert exception.message == "authentication failure"


def test_token_login_json_decode_error():
    """Test token login with invalid JSON response."""
    # Create mock response with invalid JSON
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.side_effect = JSONDecodeError("Invalid JSON", "", 0)
    mock_response.text = "Not valid JSON"

    # Create and start the generator
    token_gen = token_login(
        "test",
        {"grant_type": "password", "username": "user@example.com"},
        "test_consumer_key"
    )

    # First yield should be a request
    next(token_gen)  # We don't need the request object here

    # Send the mock response and expect an exception
    with pytest.raises(SalesforceAuthenticationFailed):
        token_gen.send(mock_response)


def test_token_login_no_response():
    """Test token login with no response."""
    # Create and start the generator
    token_gen = token_login(
        "test",
        {"grant_type": "password", "username": "user@example.com"},
        "test_consumer_key"
    )

    # First yield should be a request
    next(token_gen)  # We don't need the request object here

    # Send None as response and expect an exception
    with pytest.raises(AuthMissingResponse, match="No response received"):
        token_gen.send(None)


def test_password_login():
    """Test password login method."""
    with patch('sf_toolkit.auth.login_oauth.token_login') as mock_token_login:
        # Setup mock token generator
        expected_token = SalesforceToken(httpx.URL("https://test.my.salesforce.com"), "test_token")

        def mock_token_generator():
            yield httpx.Request("POST", "https://test.salesforce.com/services/oauth2/token")
            return expected_token

        mock_token_login.return_value = mock_token_generator()

        # Call the function
        login_func = password_login(
            username="test@example.com",
            password="password123",
            consumer_key="test_consumer_key",
            consumer_secret="test_consumer_secret",
            domain="test"
        )

        # Get the generator
        login_gen = login_func()

        # Get the result
        result = next(login_gen)
        assert result is not None

        # Verify token_login was called with correct arguments
        mock_token_login.assert_called_once()
        args, kwargs = mock_token_login.call_args

        # Check domain and consumer key
        assert args[0] == "test"
        assert args[2] == "test_consumer_key"

        # Check token data
        token_data = args[1]
        assert token_data["grant_type"] == "password"
        assert token_data["username"] == "test@example.com"
        assert token_data["password"] == "password123"
        assert token_data["client_id"] == "test_consumer_key"
        assert token_data["client_secret"] == "test_consumer_secret"


def test_password_login_with_empty_password():
    """Test password login with empty password."""
    with patch('sf_toolkit.auth.login_oauth.token_login') as mock_token_login:
        # Setup mock token generator
        expected_token = SalesforceToken(httpx.URL("https://test.my.salesforce.com"), "test_token")

        def mock_token_generator():
            yield httpx.Request("POST", "https://test.salesforce.com/services/oauth2/token")
            return expected_token

        mock_token_login.return_value = mock_token_generator()

        # Call the function with empty password
        login_func = password_login(
            username="test@example.com",
            password="",  # Empty password
            consumer_key="test_consumer_key",
            consumer_secret="test_consumer_secret"
        )

        # Get the generator
        login_gen = login_func()

        # Get the result
        result = next(login_gen)
        assert result is not None

        # Verify token_login was called with correct arguments
        mock_token_login.assert_called_once()
        args, kwargs = mock_token_login.call_args

        # Check password is empty string
        token_data = args[1]
        assert token_data["password"] == ""


def test_client_credentials_flow_login():
    """Test client credentials flow login method."""
    with patch('sf_toolkit.auth.login_oauth.token_login') as mock_token_login:
        # Setup mock token generator
        expected_token = SalesforceToken(httpx.URL("https://test.my.salesforce.com"), "test_token")

        def mock_token_generator():
            yield httpx.Request("POST", "https://test.salesforce.com/services/oauth2/token")
            return expected_token

        mock_token_login.return_value = mock_token_generator()

        # Call the function
        login_func = client_credentials_flow_login(
            consumer_key="test_consumer_key",
            consumer_secret="test_consumer_secret",
            domain="test"
        )

        # Get the generator
        login_gen = login_func()

        # Get the result
        result = next(login_gen)
        assert result is not None

        # Verify token_login was called with correct arguments
        mock_token_login.assert_called_once()
        args, kwargs = mock_token_login.call_args

        # Check domain
        assert args[0] == "test"

        # Check token data
        token_data = args[1]
        assert token_data["grant_type"] == "client_credentials"

        # Check auth header
        headers = kwargs.get("headers")
        assert headers is not None
        assert "Authorization" in headers

        # Verify encoded auth header
        auth_header = headers["Authorization"]
        assert auth_header.startswith("Basic ")

        # Decode and check credentials
        encoded_part = auth_header.split(" ")[1]
        decoded = base64.b64decode(encoded_part).decode()
        assert decoded == "test_consumer_key:test_consumer_secret"


def test_public_key_auth_login():
    """Test public key JWT bearer flow login method."""
    with patch('sf_toolkit.auth.login_oauth.token_login') as mock_token_login, \
         patch('sf_toolkit.auth.login_oauth.jwt.encode') as mock_jwt_encode:

        # Setup mock JWT encoded output
        mock_jwt_encode.return_value = "mock.jwt.token"

        # Setup mock token generator
        expected_token = SalesforceToken(httpx.URL("https://test.my.salesforce.com"), "test_token")

        def mock_token_generator():
            yield httpx.Request("POST", "https://test.salesforce.com/services/oauth2/token")
            return expected_token

        mock_token_login.return_value = mock_token_generator()

        # Create a test private key
        private_key = "test private key"

        # Current time for JWT claims
        current_time = int(time.time())

        # Mock time.time() to return a fixed value
        with patch('sf_toolkit.auth.login_oauth.time.time', return_value=current_time):
            # Call the function
            login_func = public_key_auth_login(
                username="test@example.com",
                consumer_key="test_consumer_key",
                private_key=private_key,
                domain="test"
            )

            # Get the generator
            login_gen = login_func()

            # Start the generator
            login_gen.send(None)  # Start the generator

            # Verify token_login was called with correct arguments
            mock_token_login.assert_called_once()
            args, kwargs = mock_token_login.call_args

            # Check domain and consumer key
            assert args[0] == "test"
            assert args[2] == "test_consumer_key"

            # Check token data
            token_data = args[1]
            assert token_data["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
            assert token_data["assertion"] == "mock.jwt.token"

            # Verify JWT encode was called with correct claims
            mock_jwt_encode.assert_called_once()
            jwt_args, jwt_kwargs = mock_jwt_encode.call_args

            # Check JWT claims
            claims = jwt_args[0]
            assert claims["iss"] == "test_consumer_key"
            assert claims["sub"] == "test@example.com"
            assert claims["aud"] == "https://test.salesforce.com"
            assert claims["exp"] == current_time + 3600

            # Check JWT signing key and algorithm
            assert jwt_args[1] == private_key
            assert jwt_kwargs["algorithm"] == "RS256"


def test_lazy_oauth_login_public_key():
    """Test lazy_oauth_login with public key parameters."""
    with patch('sf_toolkit.auth.login_oauth.public_key_auth_login') as mock_login:
        mock_login.return_value = "mock_login_function"

        # Call with public key parameters
        result = lazy_oauth_login(
            username="test@example.com",
            consumer_key="test_consumer_key",
            private_key="test_private_key",
            domain="test"
        )

        # Verify the correct login method was called
        mock_login.assert_called_once_with(
            username="test@example.com",
            consumer_key="test_consumer_key",
            private_key="test_private_key",
            domain="test"
        )

        assert result == "mock_login_function"


def test_lazy_oauth_login_password():
    """Test lazy_oauth_login with password parameters."""
    with patch('sf_toolkit.auth.login_oauth.password_login') as mock_login:
        mock_login.return_value = "mock_login_function"

        # Call with password parameters
        result = lazy_oauth_login(
            username="test@example.com",
            password="test_password",
            consumer_key="test_consumer_key",
            consumer_secret="test_consumer_secret",
            domain="test"
        )

        # Verify the correct login method was called
        mock_login.assert_called_once_with(
            username="test@example.com",
            password="test_password",
            consumer_key="test_consumer_key",
            consumer_secret="test_consumer_secret",
            domain="test"
        )

        assert result == "mock_login_function"


def test_lazy_oauth_login_client_credentials():
    """Test lazy_oauth_login with client credentials parameters."""
    with patch('sf_toolkit.auth.login_oauth.client_credentials_flow_login') as mock_login:
        mock_login.return_value = "mock_login_function"

        # Call with client credentials parameters (no username)
        result = lazy_oauth_login(
            consumer_key="test_consumer_key",
            consumer_secret="test_consumer_secret",
            domain="test"
        )

        # Verify the correct login method was called
        mock_login.assert_called_once_with(
            consumer_key="test_consumer_key",
            consumer_secret="test_consumer_secret",
            domain="test"
        )

        assert result == "mock_login_function"


def test_lazy_oauth_login_invalid_params():
    """Test lazy_oauth_login with invalid parameters."""
    # Call with invalid parameters
    with pytest.raises(LazyParametersMissing, match="Unable to determine authentication method"):
        lazy_oauth_login(
            username="test@example.com",  # Username but no password or private key
            consumer_key="test_consumer_key"
        )


def test_user_hasnt_approved_consumer_warning():
    """Test warning when user hasn't approved the consumer."""
    # Create mock error response for unapproved consumer
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "error": "invalid_grant",
        "error_description": "user hasn't approved this consumer"
    }

    # Create and start the generator
    token_gen = token_login(
        "test",
        {"grant_type": "password", "username": "user@example.com"},
        "test_consumer_key"
    )

    # First yield should be a request
    next(token_gen)  # We don't need the request object here

    # Send the mock error response and expect a warning followed by exception
    with pytest.warns(UserWarning, match="authorize"), \
         pytest.raises(SalesforceAuthenticationFailed):
        token_gen.send(mock_response)
