import pytest
import httpx
from unittest.mock import patch, Mock
from lxml.etree import XMLSyntaxError

from sf_toolkit.auth.login_soap import (
    security_token_login,
    ip_filtering_org_login,
    ip_filtering_non_service_login,
    soap_login,
    get_xml_element_value,
    DEFAULT_CLIENT_ID_PREFIX
)
from sf_toolkit.auth.types import SalesforceToken
from sf_toolkit.exceptions import SalesforceAuthenticationFailed


def test_get_element_value_success():
    """Test successfully extracting a value from XML"""
    xml = '<?xml version="1.0" encoding="UTF-8"?><root><element>test_value</element></root>'
    value = get_xml_element_value(xml, "element")
    assert value == "test_value"


def test_get_element_value_not_found():
    """Test extracting a value from XML when the element doesn't exist"""
    xml = '<?xml version="1.0" encoding="UTF-8"?><root><element>test_value</element></root>'
    value = get_xml_element_value(xml, "missing_element")
    assert value is None


def test_get_element_value_invalid_xml():
    """Test handling invalid XML"""
    with pytest.raises(XMLSyntaxError):
        get_xml_element_value("not valid xml", "element")


@patch('sf_toolkit.auth.login_soap.soap_login')
def test_security_token_login(mock_soap_login):
    """Test security token login method"""
    # Setup mock
    expected_token = SalesforceToken(httpx.URL("https://test.salesforce.com"), "test_token")
    def mock_soap_login_generator():
        yield expected_token
    mock_soap_login.return_value = mock_soap_login_generator()

    # Call the function
    login_gen = security_token_login(
        username="test@example.com",
        password="password123",
        security_token="SECURITY_TOKEN",
        client_id="test_client",
        domain="test",
        api_version=57.0
    )

    # Verify the generator returns the expected token
    assert next(login_gen) == expected_token

    # Check mock was called with correct arguments
    mock_soap_login.assert_called_once()
    args = mock_soap_login.call_args[0]
    assert args[0] == "test"  # domain
    assert args[1] == 57.0  # api_version

    # Verify request body contains expected values
    request_body = args[2]
    assert "test@example.com" in request_body
    assert "password123SECURITY_TOKEN" in request_body
    assert f"{DEFAULT_CLIENT_ID_PREFIX}/test_client" in request_body


@patch('sf_toolkit.auth.login_soap.soap_login')
def test_security_token_login_default_client_id(mock_soap_login):
    """Test security token login with default client ID"""
    # Setup mock
    expected_token = SalesforceToken(httpx.URL("https://test.salesforce.com"), "test_token")
    def mock_soap_login_generator():
        yield expected_token
    mock_soap_login.return_value = mock_soap_login_generator()

    # Call the function with no client_id
    login_gen = security_token_login(
        username="test@example.com",
        password="password123",
        security_token="SECURITY_TOKEN"
    )

    # Verify the generator returns the expected token
    assert next(login_gen) == expected_token

    # Check request body contains default client ID
    request_body = mock_soap_login.call_args[0][2]
    assert DEFAULT_CLIENT_ID_PREFIX in request_body
    assert "/" not in request_body.split(DEFAULT_CLIENT_ID_PREFIX)[1].split("<")[0]


@patch('sf_toolkit.auth.login_soap.soap_login')
def test_ip_filtering_org_login(mock_soap_login):
    """Test IP filtering login with org ID"""
    # Setup mock
    expected_token = SalesforceToken(httpx.URL("https://test.salesforce.com"), "test_token")
    def mock_soap_login_generator():
        yield expected_token
    mock_soap_login.return_value = mock_soap_login_generator()

    # Call the function
    login_gen = ip_filtering_org_login(
        username="test@example.com",
        password="password123",
        organizationId="00D000000000001",
        client_id="test_client",
        domain="test",
        api_version=57.0
    )

    # Verify the generator returns the expected token
    assert next(login_gen) == expected_token

    # Check mock was called with correct arguments
    mock_soap_login.assert_called_once()
    args = mock_soap_login.call_args[0]

    # Verify request body contains expected values
    request_body = args[2]
    assert "test@example.com" in request_body
    assert "password123" in request_body
    assert "00D000000000001" in request_body
    assert f"{DEFAULT_CLIENT_ID_PREFIX}/test_client" in request_body


@patch('sf_toolkit.auth.login_soap.soap_login')
def test_ip_filtering_non_service_login(mock_soap_login):
    """Test IP filtering login without org ID"""
    # Setup mock
    expected_token = SalesforceToken(httpx.URL("https://test.salesforce.com"), "test_token")
    def mock_soap_login_generator():
        yield expected_token
    mock_soap_login.return_value = mock_soap_login_generator()

    # Call the function
    login_gen = ip_filtering_non_service_login(
        username="test@example.com",
        password="password123",
        client_id="test_client",
        domain="test",
        api_version=57.0
    )

    # Verify the generator returns the expected token
    assert next(login_gen) == expected_token

    # Check mock was called with correct arguments
    mock_soap_login.assert_called_once()
    args = mock_soap_login.call_args[0]

    # Verify request body contains expected values
    request_body = args[2]
    assert "test@example.com" in request_body
    assert "password123" in request_body
    assert f"{DEFAULT_CLIENT_ID_PREFIX}/test_client" in request_body


def test_soap_login_success():
    """Test successful SOAP login flow"""
    # Mock successful response
    mock_response = Mock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
    <Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:sf="urn:partner.soap.sforce.com">
        <Body>
            <loginResponse>
                <result>
                    <sessionId>SESSION_ID_12345</sessionId>
                    <serverUrl>https://test.instance.salesforce.com/services/Soap/u/57.0/00D000000000001</serverUrl>
                </result>
            </loginResponse>
        </Body>
    </Envelope>
    """

    # Create and start the generator
    login_gen = soap_login("test", 57.0, "<soap_request_body>")

    # First yield should be a request to be sent
    request = next(login_gen)
    assert isinstance(request, httpx.Request)
    assert request.method == "POST"
    assert request.url == "https://test.salesforce.com/services/Soap/u/57.0"
    assert request.content == b"<soap_request_body>"

    # Send the mock response
    token = None
    try:
        login_gen.send(mock_response)
    except StopIteration as e:
        token = e.value
    finally:
        assert token is not None

    # Verify the returned token
    assert isinstance(token, SalesforceToken)
    assert token.token == "SESSION_ID_12345"
    assert token.instance.host == "test.instance.salesforce.com"


def test_soap_login_error():
    """Test SOAP login with error response"""
    # Mock error response
    mock_response = Mock(spec=httpx.Response)
    mock_response.is_success = False
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
    <Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
              xmlns:sf="urn:partner.soap.sforce.com">
        <Body>
            <Fault>
                <faultcode>sf:INVALID_LOGIN</faultcode>
                <faultstring>INVALID_LOGIN</faultstring>
                <detail>
                    <sf:exceptionCode>INVALID_LOGIN</sf:exceptionCode>
                    <sf:exceptionMessage>Invalid username or password</sf:exceptionMessage>
                </detail>
            </Fault>
        </Body>
    </Envelope>
    """

    # Create and start the generator
    login_gen = soap_login("test", 57.0, "<soap_request_body>")

    # First yield should be a request to be sent
    next(login_gen)

    # Send the mock error response and expect an exception
    with pytest.raises(SalesforceAuthenticationFailed) as excinfo:
        login_gen.send(mock_response)

        # Verify exception details
        exception = excinfo.value
        assert exception.code == "INVALID_LOGIN"
        assert exception.message == "Invalid username or password"


def test_soap_login_missing_session_data():
    """Test SOAP login with missing session data in response"""
    # Mock response with missing data
    mock_response = Mock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
    <Envelope xmlns="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
        <Body>
            <loginResponse>
                <result>
                    <!-- Missing sessionId and serverUrl -->
                </result>
            </loginResponse>
        </Body>
    </Envelope>
    """

    # Create and start the generator
    login_gen = soap_login("test", 57.0, "<soap_request_body>")

    # First yield should be a request to be sent
    next(login_gen)

    # Send the mock response with missing data and expect an assertion error
    with pytest.raises(AssertionError):
        login_gen.send(mock_response)
