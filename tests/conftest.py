from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import zipfile
import random
import string

import pytest

from sf_toolkit.client import AsyncSalesforceClient, SalesforceClient
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


def mock_client(spec_cls: type):
    # Create a mock SalesforceClient for testing
    mock_client = MagicMock(spec=spec_cls)
    mock_client.data_url = _url = "/services/data/v65.0"
    mock_client.sobjects_url = f"{_url}/sobjects"
    mock_client.tooling_url = f"{_url}/tooling"
    mock_client.metadata_url = f"{_url}/metadata"
    mock_client.composite_sobjects_url = MagicMock(
        return_value=f"{_url}/composite/sobjects/Account"
    )
    mock_client.connection_name = spec_cls.DEFAULT_CONNECTION_NAME or "default"

    # Keep a reference to the original _connections dictionary to restore later
    original_connections = spec_cls._connections

    # Add the mock client to the _connections dictionary directly
    spec_cls._connections = {spec_cls.DEFAULT_CONNECTION_NAME or "default": mock_client}

    yield mock_client

    # Restore the original _connections dictionary
    spec_cls._connections = original_connections


@pytest.fixture()
def mock_sf_client():
    yield from mock_client(SalesforceClient)


@pytest.fixture()
def mock_async_client():
    yield from mock_client(AsyncSalesforceClient)


@pytest.fixture
def mock_zip_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Generates a temp zip file that is torn down after the test"""
    random_filename = "".join(random.choices(string.ascii_letters, k=10)) + ".zip"
    filepath = tmp_path / random_filename
    with zipfile.ZipFile(filepath, "w") as zipf:
        zipf.writestr("example.txt", "Hello, World!")
    yield filepath
    filepath.unlink
