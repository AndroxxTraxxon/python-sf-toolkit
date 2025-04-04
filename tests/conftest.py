import pytest
from sf_toolkit.client import SalesforceClient
from sf_toolkit.auth.login_cli import cli_login

@pytest.fixture
def sf_client():
    """Fixture that yields a SalesforceClient connected to default SF CLI org"""
    with SalesforceClient(login=cli_login()) as client:
        yield client
