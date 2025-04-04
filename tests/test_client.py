from httpx import URL
import httpx
from sf_toolkit.apimodels import ApiVersion
from sf_toolkit.auth.types import SalesforceToken
from sf_toolkit.client import SalesforceClient



def test_client_context_manager(mocker):
    """Test that the client context manager correctly initializes"""

    # Create a mock userinfo with all required fields
    mock_userinfo = {
        "name": "Test User",
        "preferred_username": "test@example.com",
        "user_id": "001XXXXXXXXXXXX",
        "email": "test@example.com",
        "organization_id": "00DXXXXXXXXXXXX",
        "sub": "https://login.salesforce.com/id/00DXXXXXXXXXXXX/001XXXXXXXXXXXX",
        "email_verified": True,
        "given_name": "Test",
        "family_name": "User",
        "zoneinfo": "America/Los_Angeles",
        "photos": {"picture": "https://example.com/picture.jpg"},
        "profile": "https://example.com/profile",
        "picture": "https://example.com/picture.jpg",
        "address": {"country": "US"},
        "urls": {"enterprise": "https://test.salesforce.com"},
        "active": True,
        "user_type": "STANDARD",
        "language": "en_US",
        "locale": "en_US",
        "utcOffset": -28800000,
        "updated_at": "2023-01-01T00:00:00Z"
    }

    # Set up mock responses
    mock_response_userinfo = mocker.Mock()
    mock_response_userinfo.json.return_value = mock_userinfo

    mock_response_versions = mocker.Mock()
    mock_response_versions.json.return_value = [
        {"version": "50.0", "label": "Winter '21", "url": "/services/data/v50.0"},
        {"version": "51.0", "label": "Spring '21", "url": "/services/data/v51.0"},
        {"version": "52.0", "label": "Summer '21", "url": "/services/data/v52.0"}
    ]

    # Mock the send method instead of request
    mock_send = mocker.patch.object(SalesforceClient, 'send')

    # Configure the mock to return different responses for different calls
    mock_send.side_effect = [mock_response_userinfo, mock_response_versions]

    # Create client with mock token
    with SalesforceClient(token=SalesforceToken(
        URL("https://test.salesforce.com"), "mock_access_token"
    )) as client:
        # Verify client has userinfo and api_version configured
        assert isinstance(client.api_version, ApiVersion)
        assert client.api_version.version == 52.0  # Should use the latest version

        # Verify the send method was called for each request
        assert mock_send.call_count == 2
        # Assert that the first call was to userinfo endpoint
        userinfo_request: httpx.Request = mock_send.call_args_list[0][0][0]
        assert userinfo_request.url.path.endswith("/oauth2/userinfo")

        # Assert that the second call was to versions endpoint
        versions_request = mock_send.call_args_list[1][0][0]
        assert versions_request.url.path.endswith("/services/data")
