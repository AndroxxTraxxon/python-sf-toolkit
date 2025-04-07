import httpx
import pytest
from unittest.mock import MagicMock  # , AsyncMock

from sf_toolkit.auth.httpx import SalesforceAuth
from sf_toolkit.auth.types import SalesforceToken


def test_salesforce_auth_init():
    """Test the initialization of SalesforceAuth."""
    login = MagicMock()
    token = SalesforceToken(httpx.URL("https://test.instance"), token="test_token")
    callback = MagicMock()

    auth = SalesforceAuth(login=login, session_token=token, callback=callback)

    assert auth.login == login
    assert auth.token == token
    assert auth.callback == callback


def test_auth_flow_with_token():
    """Test auth flow when token is already available."""
    token = SalesforceToken(httpx.URL("https://test.instance"), token="test_token")
    auth = SalesforceAuth(session_token=token)

    request = httpx.Request("GET", "https://example.com")
    flow = auth.auth_flow(request)

    # Get the modified request
    modified_request = next(flow)

    assert modified_request.headers["Authorization"] == f"Bearer {token.token}"


def test_auth_flow_initial_login():
    """Test auth flow when initial login is required."""
    token = SalesforceToken(httpx.URL("https://test.instance"), token="test_token")

    # Mock login generator function
    def mock_login():
        login_request = httpx.Request("POST", "https://login.salesforce.com")
        yield login_request
        # Process response here if needed
        return token

    callback = MagicMock()
    auth = SalesforceAuth(login=mock_login, callback=callback)

    request = httpx.Request("GET", "https://example.com")
    flow = auth.auth_flow(request)

    # Get the login request
    login_request = next(flow)
    assert login_request.method == "POST"
    assert login_request.url == "https://login.salesforce.com"

    # Simulate response to login request
    login_response = httpx.Response(200, json={"access_token": "test_token"})

    # Send the response and get the modified original request
    modified_request = flow.send(login_response)

    assert auth.token == token
    assert modified_request.headers["Authorization"] == f"Bearer {token.token}"
    callback.assert_called_once_with(token)


def test_auth_flow_token_refresh():
    """Test auth flow when token refresh is required."""
    initial_token = SalesforceToken(
        httpx.URL("https://test.instance"), token="initial_token"
    )
    new_token = SalesforceToken(httpx.URL("https://test.instance"), token="new_token")

    # Mock login generator function for refresh
    def mock_login():
        login_request = httpx.Request("POST", "https://login.salesforce.com")
        yield login_request
        # Process response here if needed
        return new_token

    callback = MagicMock()
    auth = SalesforceAuth(
        login=mock_login, session_token=initial_token, callback=callback
    )

    request = httpx.Request("GET", "https://example.com")
    flow = auth.auth_flow(request)

    # Get the modified request with initial token
    modified_request = next(flow)
    assert modified_request.headers["Authorization"] == f"Bearer {initial_token.token}"

    # Simulate 401 response with INVALID_SESSION_ID
    error_response = httpx.Response(401, json=[{"errorDetails": "INVALID_SESSION_ID"}])

    # Send the error response and get the login request
    login_request = flow.send(error_response)
    assert login_request.method == "POST"
    assert login_request.url == "https://login.salesforce.com"

    # Simulate response to login request
    login_response = httpx.Response(200, json={"access_token": "new_token"})

    # Send the response and get the modified original request with new token
    refreshed_request = flow.send(login_response)

    assert auth.token == new_token
    assert refreshed_request.headers["Authorization"] == f"Bearer {new_token.token}"
    callback.assert_called_once_with(new_token)


def test_auth_flow_no_login_method():
    """Test auth flow when no token and no login method is provided."""
    auth = SalesforceAuth()

    request = httpx.Request("GET", "https://example.com")
    flow = auth.auth_flow(request)

    with pytest.raises(AssertionError, match="No login method provided"):
        next(flow)
