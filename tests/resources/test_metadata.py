from unittest.mock import Mock, ANY

import pytest

from sf_toolkit.resources.metadata import (
    DeployResult,
    MetadataResource,
    DeployOptions,
    DeployRequest,
)


def test_deploy_success(mock_sf_client, mock_zip_file):
    """Test successful execution of anonymous Apex code."""
    # Setup mock response for successful execution
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "0Afxx00000001VPCAY",
        "deployOptions": {
            "checkOnly": False,
            "singlePackage": False,
            "allowMissingFiles": False,
            "performRetrieve": False,
            "autoUpdatePackage": False,
            "rollbackOnError": True,
            "ignoreWarnings": False,
            "purgeOnDelete": False,
            "runAllTests": False,
        },
        "deployResult": {
            "id": "0Afxx00000001VPCAY",
            "success": False,
            "checkOnly": False,
            "ignoreWarnings": False,
            "rollbackOnError": True,
            "status": "Pending",
            "runTestsEnabled": False,
            "done": False,
        },
    }
    mock_sf_client.post.return_value = mock_response

    # Create Tooling instance with mock client
    mock_sf_client.metadata = MetadataResource(mock_sf_client)

    # Execute anonymous code
    result = mock_sf_client.metadata.deploy(
        mock_zip_file,
        DeployOptions(singlePackage=True),
    )

    assert isinstance(result, DeployRequest)
    assert result.id == "0Afxx00000001VPCAY"
    assert isinstance(result.deployOptions, DeployOptions)
    assert isinstance(result.deployResult, DeployResult)
    assert result.deployResult.status == "Pending"

    # Verify the API call was made correctly
    mock_sf_client.post.assert_called_once_with(
        mock_sf_client.metadata_url + "/deployRequest",
        files=[
            (
                "json",
                (
                    None,
                    '{"deployOptions": {"singlePackage": true}}',
                    "application/json",
                ),
            ),
            ("file", (str(mock_zip_file.name), ANY, "application/zip")),
        ],
    )


def test_deploy_success_kwarg_options(mock_sf_client, mock_zip_file):
    """Test successful execution of anonymous Apex code."""
    # Setup mock response for successful execution
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "0Afxx00000001VPCAY",
        "deployOptions": {
            "checkOnly": False,
            "singlePackage": False,
            "allowMissingFiles": False,
            "performRetrieve": False,
            "autoUpdatePackage": False,
            "rollbackOnError": True,
            "ignoreWarnings": False,
            "purgeOnDelete": False,
            "runAllTests": False,
        },
        "deployResult": {
            "id": "0Afxx00000001VPCAY",
            "success": False,
            "checkOnly": False,
            "ignoreWarnings": False,
            "rollbackOnError": True,
            "status": "Pending",
            "runTestsEnabled": False,
            "done": False,
        },
    }
    mock_sf_client.post.return_value = mock_response

    # Create MetadataResource instance with mock client
    mock_sf_client.metadata = MetadataResource(mock_sf_client)

    # Execute anonymous code
    result = mock_sf_client.metadata.deploy(
        mock_zip_file,
        singlePackage=True,
    )

    assert isinstance(result, DeployRequest)
    assert result.id == "0Afxx00000001VPCAY"
    assert isinstance(result.deployOptions, DeployOptions)
    assert isinstance(result.deployResult, DeployResult)
    assert result.deployResult.status == "Pending"

    # Verify the API call was made correctly
    mock_sf_client.post.assert_called_once_with(
        mock_sf_client.metadata_url + "/deployRequest",
        files=[
            (
                "json",
                (
                    None,
                    '{"deployOptions": {"singlePackage": true}}',
                    "application/json",
                ),
            ),
            ("file", (str(mock_zip_file.name), ANY, "application/zip")),
        ],
    )


def test_get_current_deploy_status(mock_sf_client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "0Afxx00000000lWCAQ",
        "url": "https://example.my.salesforce.com/services/data/v57.0/metadata/deployRequest/0Afxx00000000lWCAQ?includeDetails=true",
        "deployResult": {
            "checkOnly": False,
            "ignoreWarnings": False,
            "rollbackOnError": False,
            "status": "InProgress",
            "numberComponentsDeployed": 10,
            "numberComponentsTotal": 1032,
            "numberComponentErrors": 0,
            "numberTestsCompleted": 45,
            "numberTestsTotal": 135,
            "numberTestErrors": 0,
            "details": {
                "componentFailures": [],
                "componentSuccesses": [],
                "retrieveResult": None,
                "runTestResult": {"numTestsRun": 0, "successes": [], "failures": []},
            },
            "createdDate": "2017-10-10T08:22Z",
            "startDate": "2017-10-10T08:22Z",
            "lastModifiedDate": "2017-10-10T08:44Z",
            "completedDate": "2017-10-10T08:44Z",
            "errorStatusCode": None,
            "errorMessage": None,
            "stateDetail": "Processing Type: Apex Component",
            "createdBy": "005xx0000001Sv1",
            "createdByName": "stephanie stevens",
            "canceledBy": None,
            "canceledByName": None,
            "runTestsEnabled": None,
        },
        "deployOptions": {
            "allowMissingFiles": False,
            "autoUpdatePackage": False,
            "checkOnly": True,
            "ignoreWarnings": False,
            "performRetrieve": False,
            "purgeOnDelete": False,
            "rollbackOnError": False,
            "runTests": None,
            "singlePackage": True,
            "testLevel": "RunAllTestsInOrg",
        },
    }

    mock_sf_client.get.return_value = mock_response

    mock_deploy_request = DeployRequest(id="0Afxx00000001VPCAY")

    refreshed_request = mock_deploy_request.current_status(include_details=True)

    assert isinstance(refreshed_request, DeployRequest)

    mock_sf_client.get.assert_called_once()

    assert isinstance(refreshed_request.current_status(), DeployRequest)


def test_cancel_deploy(mock_sf_client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "0Afxx00000000lWCAQ",
        "url": "https://host/services/data/vXX.0/metadata/deployRequest/0Afxx00000000lWCAQ",
        "deployResult": {
            "checkOnly": False,
            "ignoreWarnings": False,
            "rollbackOnError": False,
            "status": "Canceling",  # or Canceled
            "numberComponentsDeployed": 10,
            "numberComponentsTotal": 1032,
            "numberComponentErrors": 0,
            "numberTestsCompleted": 45,
            "numberTestsTotal": 135,
            "numberTestErrors": 0,
            "details": {
                "componentFailures": [],
                "componentSuccesses": [],
                "retrieveResult": None,
                "runTestResult": {"numTestsRun": 0, "successes": [], "failures": []},
            },
            "createdDate": "2017-10-10T08:22Z",
            "startDate": "2017-10-10T08:22Z",
            "lastModifiedDate": "2017-10-10T08:44Z",
            "completedDate": "2017-10-10T08:44Z",
            "errorStatusCode": None,
            "errorMessage": None,
            "stateDetail": "Processing Type: Apex Component",
            "createdBy": "005x0000001Sv1m",
            "createdByName": "steve stevens",
            "canceledBy": None,
            "canceledByName": None,
            "runTestsEnabled": None,
        },
    }
    mock_response.status_code = 202

    mock_sf_client.patch.return_value = mock_response

    mock_deploy_request = DeployRequest(id="0Afxx00000000lWCAQ")

    canceled_request = mock_deploy_request.cancel(None)

    mock_sf_client.patch.assert_called_once()
    assert isinstance(canceled_request, DeployRequest)
    assert canceled_request._connection is mock_sf_client
    assert canceled_request.deployResult.status == "Canceling"

    mock_response.status_code = 401

    with pytest.raises(ValueError):
        canceled_request.cancel()


def test_validated_quick_deploy(mock_sf_client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "validatedDeployRequestId": "0Afxx00000000lWCAQ",
        "id": "0Afxx00000000lWMEM",
        "url": "https://host/services/data/vXX.0/metadata/deployRequest/0Afxx00000000lWMEM",
        "deployOptions": {
            "allowMissingFiles": False,
            "autoUpdatePackage": False,
            "checkOnly": True,
            "ignoreWarnings": False,
            "performRetrieve": False,
            "purgeOnDelete": False,
            "rollbackOnError": False,
            "runTests": None,
            "singlePackage": True,
            "testLevel": "RunAllTestsInOrg",
        },
    }

    mock_response.status_code = 201

    mock_sf_client.post.return_value = mock_response

    mock_validated_request = DeployRequest(
        id="0Afxx00000000lWCAQ", deployOptions={"checkOnly": True}
    )

    commit_request = mock_validated_request.quick_deploy_validated()
    mock_sf_client.post.assert_called_once()
    assert isinstance(commit_request, DeployRequest)

    mock_validated_request._connection = mock_sf_client
    commit_request = mock_validated_request.quick_deploy_validated()
    assert isinstance(commit_request, DeployRequest)
