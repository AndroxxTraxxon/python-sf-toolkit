import json
import httpx
import pytest
from unittest.mock import patch

from sf_toolkit.auth._httpx import SalesforceAuth
from sf_toolkit.auth.login_cli import cli_login
from sf_toolkit.auth.types import SalesforceToken


def test_cli_login_success():
    """Test that cli_login returns a valid login function when SF CLI is available."""
    with patch("sf_toolkit.auth.login_cli.which", return_value="/usr/bin/sf"):
        login_func = cli_login()
        assert callable(login_func)


def test_cli_login_no_sf_executable():
    """Test that cli_login raises an error when SF CLI is not available."""
    with patch("sf_toolkit.auth.login_cli.which", return_value=None):
        with pytest.raises(ValueError, match="Could not find `sf` executable"):
            cli_login()


def test_cli_login_with_alias():
    """Test that cli_login constructs the command with the alias parameter."""
    with (
        patch("sf_toolkit.auth.login_cli.which", return_value="/usr/bin/sf"),
        patch("sf_toolkit.auth.login_cli.subprocess_run") as mock_run,
    ):
        mock_run.return_value.stdout = json.dumps(
            {
                "status": 0,
                "result": {
                    "connectedStatus": "Connected",
                    "accessToken": "test_token",
                    "instanceUrl": "https://test.salesforce.com",
                },
            }
        ).encode("utf-8")

        login_func = cli_login("my-alias")
        login_gen = login_func()
        iter_count = 0
        try:
            while True:
                next(login_gen)  # Exhaust the generator
                iter_count += 1
        except StopIteration as result:
            generated_token: SalesforceToken = result.value
        assert iter_count <= 2
        mock_run.assert_called_once()
        # Verify the command included the alias
        cmd_args = mock_run.call_args[0][0]
        assert "-o" in cmd_args
        assert "my-alias" in cmd_args

        assert generated_token is not None
        assert generated_token.token == "test_token"
        assert generated_token.instance.host == "test.salesforce.com"


def test_cli_login_command_failure():
    """Test handling of CLI command failures."""
    with patch("sf_toolkit.auth.login_cli.which", return_value="/usr/bin/sf"):
        with patch("sf_toolkit.auth.login_cli.subprocess_run") as mock_run:
            mock_run.return_value.stdout = json.dumps(
                {
                    "status": 1,
                    "name": "LoginFailedError",
                    "message": "Authentication failed",
                }
            ).encode("utf-8")

            login_func = cli_login()
            login_gen = login_func()

            with pytest.raises(Exception, match="Failed to get credentials"):
                next(login_gen)  # Start the generator
                next(login_gen)


def test_cli_login_disconnected_status():
    """Test handling of disconnected status response."""
    with patch("sf_toolkit.auth.login_cli.which", return_value="/usr/bin/sf"):
        with patch("sf_toolkit.auth.login_cli.subprocess_run") as mock_run:
            mock_run.return_value.stdout = json.dumps(
                {
                    "status": 0,
                    "warnings": ["Session expired"],
                    "result": {
                        "connectedStatus": "Disconnected",
                        "instanceUrl": "https://test.salesforce.com",
                        "username": "test@example.com",
                    },
                }
            ).encode("utf-8")

            login_func = cli_login()
            login_gen = login_func()

            with pytest.raises(Exception, match="Unable to connect"):
                next(login_gen)


def test_auth_flow_with_cli_login():
    """Test auth flow using the CLI login method."""
    test_cli_token = "1234567890qwertyuioasdfghjklzxcvbnm"
    with patch("sf_toolkit.auth.login_cli.which", return_value="/usr/bin/sf"):
        with patch("sf_toolkit.auth.login_cli.subprocess_run") as mock_run:
            mock_run.return_value.stdout = json.dumps(
                {
                    "status": 0,
                    "result": {
                        "connectedStatus": "Connected",
                        "accessToken": test_cli_token,
                        "instanceUrl": "https://test.salesforce.com",
                    },
                }
            ).encode("utf-8")

            login_func = cli_login()
            auth = SalesforceAuth(login=login_func)
            request = httpx.Request(
                "GET", "https://test.salesforce.com/services/data/v57.0/query"
            )

            # Get the generator
            flow = auth.auth_flow(request)

            # Send None to complete the cli_login generator
            modified_request = next(flow)

            # Check the modified request has the authorization header
            assert "Authorization" in modified_request.headers
            assert (
                modified_request.headers["Authorization"] == "Bearer " + test_cli_token
            )
            assert modified_request.url == request.url

            # the original request is only modified. a new request is not created.
            assert modified_request is request
