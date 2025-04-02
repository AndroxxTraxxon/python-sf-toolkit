import pytest
from sf_toolkit.client import SalesforceClient
from sf_toolkit.auth.login_cli import cli_login
import os

@pytest.mark.integration
def test_cli_login_with_default_org():
    """Test that we can log in using the default org from sf cli"""
    # Create client with CLI login method
    with SalesforceClient(login=cli_login()) as client:
        # Verify we got a valid connection
        assert client.base_url is not None
        assert client._userinfo is not None
        assert client.versions
        # Check we have API usage info
        assert hasattr(client, "api_usage")

@pytest.mark.integration
def test_cli_login_with_personal_org():
    """Test that we can log in using a specific org alias from sf cli"""
    # Skip if no personal org is configured
    if "INTEGRATION_TEST_ORG_ALIAS" not in os.environ:
        pytest.skip("PERSONAL_ORG_ALIAS environment variable not set")

    personal_alias = os.environ["INTEGRATION_TEST_ORG_ALIAS"]

    # Create client with CLI login method for specific org
    with SalesforceClient(login=cli_login(personal_alias), connection_name="integration_test") as client:
        # Verify we got a valid connection
        assert client.base_url is not None
        assert client._userinfo is not None
        assert client.versions
        # Check we have API usage info
        assert hasattr(client, "api_usage")
