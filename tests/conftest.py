from unittest.mock import MagicMock
import pytest
from sf_toolkit.client import SalesforceClient
from sf_toolkit.auth.login_cli import cli_login
from sf_toolkit.interfaces import I_SalesforceClient


@pytest.fixture(scope="session")
def cached_cli_login():
    """Fixture that caches the CLI login token for the entire test session"""
    token = None
    try:
        next(cli_login()())
    except StopIteration as result:
        token = result.value
    # Start the generator and get to the first yield point
    # Resume execution and get the token

    # Define a generator function that yields once and returns the cached token
    def _wrapper():
        def _cached_login():
            return token
            yield

        return _cached_login

    return _wrapper


@pytest.fixture
def sf_client(cached_cli_login):
    """Fixture that yields a SalesforceClient connected to default SF CLI org"""
    with SalesforceClient(login=cached_cli_login()) as client:
        yield client


@pytest.fixture()
def mock_sf_client():
    # Create a mock SalesforceClient for testing
    mock_client = MagicMock(spec=SalesforceClient)
    mock_client.sobjects_url = "/services/data/v57.0/sobjects"
    mock_client.tooling_url = "/services/data/v57.0/tooling"
    mock_client.metadata_url = "/services/data/v57.0/metadata"
    mock_client.data_url = "/services/data/v57.0/query"
    mock_client.composite_sobjects_url = MagicMock(
        return_value="/services/data/v57.0/composite/sobjects/Account"
    )

    # Keep a reference to the original _connections dictionary to restore later
    original_connections = I_SalesforceClient._connections

    # Add the mock client to the _connections dictionary directly
    I_SalesforceClient._connections = {
        SalesforceClient.DEFAULT_CONNECTION_NAME: mock_client
    }

    yield mock_client

    # Restore the original _connections dictionary
    I_SalesforceClient._connections = original_connections
