from unittest.mock import Mock

from httpx import URL
import httpx

from sf_toolkit.apimodels import ApiVersion, OrgLimits, Limit
from sf_toolkit.auth.types import SalesforceToken
from sf_toolkit.client import SalesforceClient
from sf_toolkit.resources.metadata import MetadataResource
from sf_toolkit.resources.tooling import ToolingResource


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
        "updated_at": "2023-01-01T00:00:00Z",
    }

    # Set up mock responses
    mock_response_userinfo = mocker.Mock()
    mock_response_userinfo.json.return_value = mock_userinfo

    mock_response_versions = mocker.Mock()
    mock_response_versions.json.return_value = [
        {"version": "50.0", "label": "Winter '21", "url": "/services/data/v50.0"},
        {"version": "51.0", "label": "Spring '21", "url": "/services/data/v51.0"},
        {"version": "52.0", "label": "Summer '21", "url": "/services/data/v52.0"},
    ]

    # Mock the send method instead of request
    mock_send = mocker.patch.object(SalesforceClient, "send")

    # Configure the mock to return different responses for different calls
    mock_send.side_effect = [mock_response_userinfo, mock_response_versions]

    # Create client with mock token
    with SalesforceClient(
        token=SalesforceToken(URL("https://test.salesforce.com"), "mock_access_token")
    ) as client:
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


def test_api_resource_helpers():
    client = SalesforceClient(token=SalesforceToken(URL("https://test.salesforce.com"), "mock_access_token"))

    assert client.tooling is not None
    assert client.tooling.client is client
    assert isinstance(client.tooling, ToolingResource)

    assert client.metadata is not None
    assert client.metadata.client is client
    assert isinstance(client.metadata, MetadataResource)


def test_limits():
    client = SalesforceClient(token=SalesforceToken(URL("https://test.salesforce.com"), "mock_access_token"))
    client.get = Mock()
    client.get.return_value.json.return_value = {
        "ActiveScratchOrgs": {
            "Max": 3,
            "Remaining": 3
        },
        "AnalyticsExternalDataSizeMB": {
            "Max": 40960,
            "Remaining": 40960
        },
        "ConcurrentAsyncGetReportInstances": {
            "Max": 200,
            "Remaining": 200
        },
        "ConcurrentEinsteinDataInsightsStoryCreation": {
            "Max": 5,
            "Remaining": 5
        },
        "ConcurrentEinsteinDiscoveryStoryCreation": {
            "Max": 2,
            "Remaining": 2
        },
        "ConcurrentSyncReportRuns": {
            "Max": 20,
            "Remaining": 20
        },
        "DailyAnalyticsDataflowJobExecutions": {
            "Max": 60,
            "Remaining": 60
        },
        "DailyAnalyticsUploadedFilesSizeMB": {
            "Max": 51200,
            "Remaining": 51200
        },
        "DailyFunctionsApiCallLimit" : {
          "Max" : 235000,
          "Remaining" : 235000
        },
        "DailyApiRequests": {
            "Max": 5000,
            "Remaining": 4937
        },
        "DailyAsyncApexExecutions": {
            "Max": 250000,
            "Remaining": 250000
        },
        "DailyAsyncApexTests": {
            "Max": 500,
            "Remaining": 500
        },
        "DailyBulkApiBatches": {
            "Max": 15000,
            "Remaining": 15000
        },
        "DailyBulkV2QueryFileStorageMB": {
            "Max": 976562,
            "Remaining": 976562
        },
        "DailyBulkV2QueryJobs": {
            "Max": 10000,
            "Remaining": 10000
        },
        "DailyDeliveredPlatformEvents" : {
          "Max" : 10000,
          "Remaining" : 10000
        },
        "DailyDurableGenericStreamingApiEvents": {
            "Max": 10000,
            "Remaining": 10000
        },
        "DailyDurableStreamingApiEvents": {
            "Max": 10000,
            "Remaining": 10000
        },
        "DailyEinsteinDataInsightsStoryCreation": {
            "Max": 1000,
            "Remaining": 1000
        },
        "DailyEinsteinDiscoveryPredictAPICalls": {
            "Max": 50000,
            "Remaining": 50000
        },
        "DailyEinsteinDiscoveryPredictionsByCDC": {
            "Max": 5000000,
            "Remaining": 5000000
        },
        "DailyEinsteinDiscoveryStoryCreation": {
            "Max": 100,
            "Remaining": 100
        },
        "DailyGenericStreamingApiEvents": {
            "Max": 10000,
            "Remaining": 10000
        },
        "DailyScratchOrgs": {
            "Max": 6,
            "Remaining": 6
        },
        "DailyStandardVolumePlatformEvents": {
            "Max": 10000,
            "Remaining": 10000
        },
        "DailyStreamingApiEvents": {
            "Max": 10000,
            "Remaining": 10000
        },
        "DailyWorkflowEmails": {
            "Max": 100000,
            "Remaining": 100000
        },
        "DataStorageMB": {
            "Max": 1024,
            "Remaining": 1024
        },
        "DurableStreamingApiConcurrentClients": {
            "Max": 20,
            "Remaining": 20
        },
        "FileStorageMB": {
            "Max": 1024,
            "Remaining": 1024
        },
        "HourlyAsyncReportRuns": {
            "Max": 1200,
            "Remaining": 1200
        },
        "HourlyDashboardRefreshes": {
            "Max": 200,
            "Remaining": 200
        },
        "HourlyDashboardResults": {
            "Max": 5000,
            "Remaining": 5000
        },
        "HourlyDashboardStatuses": {
            "Max": 999999999,
            "Remaining": 999999999
        },
        "HourlyLongTermIdMapping": {
            "Max": 100000,
            "Remaining": 100000
        },
        "HourlyManagedContentPublicRequests": {
            "Max": 50000,
            "Remaining": 50000
        },
        "HourlyODataCallout": {
            "Max": 20000,
            "Remaining": 20000
        },
        "HourlyPublishedPlatformEvents": {
            "Max": 50000,
            "Remaining": 50000
        },
        "HourlyPublishedStandardVolumePlatformEvents": {
            "Max": 1000,
            "Remaining": 1000
        },
        "HourlyShortTermIdMapping": {
            "Max": 100000,
            "Remaining": 100000
        },
        "HourlySyncReportRuns": {
            "Max": 500,
            "Remaining": 500
        },
        "HourlyTimeBasedWorkflow": {
            "Max": 1000,
            "Remaining": 1000
        },
        "MassEmail": {
            "Max": 5000,
            "Remaining": 5000
        },
        "MonthlyEinsteinDiscoveryStoryCreation": {
            "Max": 500,
            "Remaining": 500
        },
        "Package2VersionCreates": {
            "Max": 6,
            "Remaining": 6
        },
        "Package2VersionCreatesWithoutValidation": {
            "Max": 500,
            "Remaining": 500
        },
        "PermissionSets": {
            "Max": 1500,
            "Remaining": 1499,
            "CreateCustom": {
                "Max": 1000,
                "Remaining": 999
            }
        },
        "PlatformEventTriggersWithParallelProcessing": {
          "Max": 5,
          "Remaining": 4
        },
        "PrivateConnectOutboundCalloutHourlyLimitMB": {
            "Max": 0,
            "Remaining": 0
        },
        "SingleEmail": {
            "Max": 5000,
            "Remaining": 5000
        },
        "StreamingApiConcurrentClients": {
            "Max": 20,
            "Remaining": 20
        }
    }
    client.api_version = ApiVersion.lazy_build(63)
    limits = client.limits()

    assert isinstance(limits, OrgLimits)
    scratchOrgLimit = limits.ActiveScratchOrgs
    assert isinstance(scratchOrgLimit, Limit)
    assert scratchOrgLimit.Max == 3
    assert scratchOrgLimit.Remaining == 3
    assert not scratchOrgLimit.is_critical()

    assert isinstance(limits.PermissionSets.CreateCustom, Limit)
