import pytest
from unittest.mock import Mock, MagicMock, patch
from sf_toolkit.resources.tooling import ToolingResource
from sf_toolkit.exceptions import SalesforceError


def test_execute_anonymous_success(mock_sf_client):
    """Test successful execution of anonymous Apex code."""
    # Setup mock response for successful execution
    mock_response = Mock()
    mock_response.json.return_value = {
        "success": True,
        "compiled": True,
        "compileProblem": "",
        "exceptionMessage": "",
        "exceptionStackTrace": "",
        "line": -1,
        "column": -1,
    }
    mock_sf_client.get.return_value = mock_response

    # Create Tooling instance with mock client
    tooling = ToolingResource(mock_sf_client)

    # Execute anonymous code
    result = tooling.execute_anonymous("System.debug('Hello World');")

    # Verify the API call was made correctly
    mock_sf_client.get.assert_called_once_with(
        mock_sf_client.tooling_url + "/executeAnonymous",
        params={"anonymousBody": "System.debug('Hello World');"},
    )

    # Verify the result was processed correctly
    assert result.success
    assert result.compiled
    assert result.compileProblem == ""
    assert result.exceptionMessage == ""


def test_execute_anonymous_compile_error(mock_sf_client):
    """Test execution of Apex code with compilation errors."""
    # Setup mock response for compilation error
    mock_response = Mock()
    mock_response.json.return_value = {
        "success": False,
        "compiled": False,
        "compileProblem": "Line: 1, Column: 1: Invalid syntax",
        "exceptionMessage": "",
        "exceptionStackTrace": "",
        "line": 1,
        "column": 1,
    }
    mock_sf_client.get.return_value = mock_response

    # Create Tooling instance with mock client
    tooling = ToolingResource(mock_sf_client)

    # Execute anonymous code with compilation error
    result = tooling.execute_anonymous("Invalid Apex code;")

    # Verify the API call was made correctly
    mock_sf_client.get.assert_called_once_with(
        mock_sf_client.tooling_url + "/executeAnonymous",
        params={"anonymousBody": "Invalid Apex code;"},
    )

    # Verify the result contains compilation error information
    assert not result.success
    assert not result.compiled
    assert result.compileProblem == "Line: 1, Column: 1: Invalid syntax"
    assert result.line == 1
    assert result.column == 1


def test_execute_anonymous_runtime_error(mock_sf_client):
    """Test execution of Apex code with runtime errors."""
    # Setup mock response for runtime error
    mock_response = Mock()
    mock_response.json.return_value = {
        "success": False,
        "compiled": True,
        "compileProblem": "",
        "exceptionMessage": "System.NullPointerException",
        "exceptionStackTrace": "Class.Method: line 5, column 10",
        "line": 5,
        "column": 10,
    }
    mock_sf_client.get.return_value = mock_response

    # Create Tooling instance with mock client
    tooling = ToolingResource(mock_sf_client)

    # Execute anonymous code with runtime error
    result = tooling.execute_anonymous("String s = null; s.length();")

    # Verify the API call was made correctly
    mock_sf_client.get.assert_called_once_with(
        mock_sf_client.tooling_url + "/executeAnonymous",
        params={"anonymousBody": "String s = null; s.length();"},
    )

    # Verify the result contains runtime error information
    assert not result.success
    assert result.compiled
    assert result.exceptionMessage == "System.NullPointerException"
    assert result.exceptionStackTrace == "Class.Method: line 5, column 10"
    assert result.line == 5
    assert result.column == 10


def test_execute_anonymous_http_error(mock_sf_client):
    """Test execution with HTTP errors from Salesforce."""
    # Setup mock to raise SalesforceError
    mock_sf_client.get.side_effect = SalesforceError(
        Mock(status_code=401, text="Unauthorized"), "ExecuteAnonymous"
    )

    # Create Tooling instance with mock client
    tooling = ToolingResource(mock_sf_client)

    # Execute anonymous code should propagate the exception
    with pytest.raises(SalesforceError) as excinfo:
        tooling.execute_anonymous("System.debug('test');")

    # Verify the exception contains error details
    exception = excinfo.value
    assert exception.status_code == 401
    assert "Unauthorized" in exception.content


def test_tooling_api_resource_with_connection_string():
    """Test creating a Tooling API resource with a connection string."""
    with patch(
        "sf_toolkit.resources.base.SalesforceClient.get_connection"
    ) as mock_get_connection:
        # Setup mock client returned by get_connection
        mock_client = MagicMock()
        mock_client.tooling_url = "/services/data/v55.0/tooling"
        mock_get_connection.return_value = mock_client

        # Create Tooling instance with connection string
        tooling = ToolingResource("test_connection")

        # Verify get_connection was called with the connection string
        mock_get_connection.assert_called_once_with("test_connection")

        # Verify client was set properly
        assert tooling.client is mock_client


def test_tooling_api_resource_with_default_connection():
    """Test creating a Tooling API resource with default connection."""
    with patch(
        "sf_toolkit.resources.base.SalesforceClient.get_connection"
    ) as mock_get_connection:
        # Setup mock client returned by get_connection
        mock_client = MagicMock()
        mock_get_connection.return_value = mock_client

        # Create Tooling instance with no connection (should use default)
        tooling = ToolingResource()

        # Verify get_connection was called with None (default connection)
        mock_get_connection.assert_called_once_with(None)

        # Verify client was set properly
        assert tooling.client is mock_client
