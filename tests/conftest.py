import pytest
from sf_toolkit.client import SalesforceClient
from sf_toolkit.auth.login_cli import cli_login


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
