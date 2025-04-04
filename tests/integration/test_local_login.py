import pytest
from sf_toolkit.client import SalesforceClient
from sf_toolkit.auth.login_cli import cli_login

@pytest.mark.integration
def test_cli_login_with_default_org():
    """Test that we can log in using the default org from sf cli"""
    # Create client with CLI login method
    with SalesforceClient(login=cli_login()) as client:
        # Verify we got a valid connection
        assert client.base_url is not None
        assert client._userinfo is not None
        assert client.versions is not None
        assert len(client.versions) > 0

    assert SalesforceClient.DEFAULT_CONNECTION_NAME not in SalesforceClient._connections

@pytest.mark.integration
def test_cli_login_with_specified_alias():
    """Test that we can log in using a specific org alias from sf cli"""
    import json
    import subprocess

    # Run sf org display to get the default org
    try:
        result = subprocess.run(
            ["sf", "org", "display", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        org_info = json.loads(result.stdout)

        # Extract the alias or username from the result
        org_alias = org_info.get("result", {}).get("alias")
        if not org_alias:
            # If no alias, use the username
            org_alias = org_info.get("result", {}).get("username")

        if not org_alias:
            pytest.skip("No default org alias or username found in sf cli")
    except (subprocess.SubprocessError, json.JSONDecodeError) as e:
        pytest.skip(f"Failed to get default org from sf cli: {str(e)}")

    # Create client with CLI login method for specific org
    with SalesforceClient(login=cli_login(org_alias)) as client:
        # Verify we got a valid connection
        assert client.base_url is not None
        assert client._userinfo is not None
        assert client.versions
        # Check we have API usage info

    assert SalesforceClient.DEFAULT_CONNECTION_NAME not in SalesforceClient._connections
