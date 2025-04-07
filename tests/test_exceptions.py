import pytest
from unittest.mock import Mock
import httpx

from sf_toolkit.exceptions import (
    raise_for_status,
    SalesforceMoreThanOneRecord,
    SalesforceRecordNotModifiedSince,
    SalesforceMalformedRequest,
    SalesforceExpiredSession,
    SalesforceRefusedRequest,
    SalesforceResourceNotFound,
    SalesforceMethodNotAllowedForResource,
    SalesforceApiVersionIncompatible,
    SalesforceResourceRemoved,
    SalesforceInvalidHeaderPreconditions,
    SalesforceUriLimitExceeded,
    SalesforceUnsupportedFormat,
    SalesforceEdgeRoutingUnavailable,
    SalesforceMissingConditionalHeader,
    SalesforceHeaderLimitExceeded,
    SalesforceServerError,
    SalesforceEdgeCommFailure,
    SalesforceServerUnavailable,
    SalesforceGeneralError,
)


def create_mock_response(
    status_code: int, url_path="/test/path", text="Error message", method="GET"
):
    """Helper function to create mock httpx.Response objects"""
    mock_request = Mock()
    mock_request.method = method

    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.reason_phrase = httpx.codes.get_reason_phrase(status_code)
    mock_response.text = text
    mock_response.request = mock_request
    mock_response.is_success = 200 <= status_code < 300

    # Mock URL object with path attribute
    mock_url = Mock()
    mock_url.path = url_path
    mock_response.url = mock_url

    # Add headers for specific tests
    mock_response.headers = {}

    return mock_response


@pytest.mark.parametrize(
    "status_code,expected_exception",
    [
        (300, SalesforceMoreThanOneRecord),
        (304, SalesforceRecordNotModifiedSince),
        (400, SalesforceMalformedRequest),
        (401, SalesforceExpiredSession),
        (403, SalesforceRefusedRequest),
        (404, SalesforceResourceNotFound),
        (405, SalesforceMethodNotAllowedForResource),
        (409, SalesforceApiVersionIncompatible),
        (410, SalesforceResourceRemoved),
        (412, SalesforceInvalidHeaderPreconditions),
        (414, SalesforceUriLimitExceeded),
        (415, SalesforceUnsupportedFormat),
        (420, SalesforceEdgeRoutingUnavailable),
        (428, SalesforceMissingConditionalHeader),
        (431, SalesforceHeaderLimitExceeded),
        (500, SalesforceServerError),
        (502, SalesforceEdgeCommFailure),
        (503, SalesforceServerUnavailable),
        # Test unmapped codes
        (418, SalesforceGeneralError),  # I'm a teapot
        (429, SalesforceGeneralError),  # Too many requests
    ],
)
def test_raise_for_status(status_code, expected_exception):
    """Test that the correct exception is raised for each status code"""
    response = create_mock_response(status_code)

    with pytest.raises(expected_exception) as excinfo:
        raise_for_status(response, "TestResource")

    exception = excinfo.value
    assert exception.status_code == status_code
    assert exception.resource_name == "TestResource"
    assert exception.url_path == "/test/path"
    assert exception.content == "Error message"
    assert exception.method == "GET"


def test_exception_string_representation():
    """Test string representation of exceptions"""
    response = create_mock_response(404)

    with pytest.raises(SalesforceResourceNotFound) as excinfo:
        raise_for_status(response, "Account")

    exception = excinfo.value
    # Test string representation
    assert "Resource Account Not Found" in str(exception)
    assert "404" in str(exception)
    assert "/test/path" in str(exception)


def test_record_not_modified_since_exception():
    """Test SalesforceRecordNotModifiedSince with modified-since header"""
    response = create_mock_response(304)
    response.headers["If-Modified-Since"] = "Tue, 01 Jan 2023 00:00:00 GMT"

    with pytest.raises(SalesforceRecordNotModifiedSince) as excinfo:
        raise_for_status(response, "Contact")

    exception = excinfo.value
    assert exception.if_modified_since == "Tue, 01 Jan 2023 00:00:00 GMT"
    assert "Tue, 01 Jan 2023 00:00:00 GMT" in str(exception)


def test_general_error_truncates_long_urls():
    """Test that SalesforceGeneralError truncates long URLs in its string representation"""
    long_path = "/services/data/v56.0/" + "a" * 300
    response = create_mock_response(418, url_path=long_path)

    with pytest.raises(SalesforceGeneralError) as excinfo:
        raise_for_status(response, "LongPathResource")

    exception = excinfo.value
    # String representation should truncate the path to 255 chars for SalesforceGeneralError
    exception_str = str(exception)
    assert "..." in exception_str
    # The URL path in the output should be truncated
    assert long_path not in exception_str
    # But should contain the beginning of the path
    assert "/services/data/v56.0/" in exception_str


def test_exception_repr():
    """Test the __repr__ method of exceptions"""
    response = create_mock_response(404)

    with pytest.raises(SalesforceResourceNotFound) as excinfo:
        raise_for_status(response, "Account")

    exception = excinfo.value
    # The repr should include the class name
    assert exception.__class__.__name__ in repr(exception)
    assert str(exception) in repr(exception)


def test_different_http_methods():
    """Test exceptions with different HTTP methods"""
    for method in ["GET", "POST", "PATCH", "DELETE"]:
        response = create_mock_response(400, method=method)

        with pytest.raises(SalesforceMalformedRequest) as excinfo:
            raise_for_status(response, "Case")

        exception = excinfo.value
        # Just verify the method is stored correctly in the exception
        assert exception.method == method

        # For SalesforceGeneralError, HTTP method is included in the string representation
        # Let's test that specifically
        general_response = create_mock_response(
            418, method=method
        )  # Use a code that maps to GeneralError

        with pytest.raises(SalesforceGeneralError) as excinfo:
            raise_for_status(general_response, "Case")

        general_exception = excinfo.value
        assert method.upper() in str(general_exception)
