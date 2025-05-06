from unittest.mock import Mock, ANY

from sf_toolkit.resources.metadata import DeployResult, MetadataResource, DeployOptions, DeployRequest

def test_deploy_success(mock_sf_client, mock_zip_file):
    """Test successful execution of anonymous Apex code."""
    # Setup mock response for successful execution
    mock_response = Mock()
    mock_response.json.return_value = { "id" : "0Afxx00000001VPCAY",
      "deployOptions" :
       { "checkOnly" : False,
         "singlePackage" : False,
         "allowMissingFiles" : False,
         "performRetrieve" : False,
         "autoUpdatePackage" : False,
         "rollbackOnError" : True,
         "ignoreWarnings" : False,
         "purgeOnDelete" : False,
         "runAllTests" : False },
      "deployResult" :
       { "id" : "0Afxx00000001VPCAY",
         "success" : False,
         "checkOnly" : False,
         "ignoreWarnings" : False,
         "rollbackOnError" : True,
         "status" : "Pending",
         "runTestsEnabled" : False,
         "done" : False } }
    mock_sf_client.post.return_value = mock_response

    # Create Tooling instance with mock client
    tooling = MetadataResource(mock_sf_client)

    # Execute anonymous code
    result = tooling.request_deploy(
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
            ('json', (None, '{"deployOptions": {"singlePackage": true}}', 'application/json')),
            ('file', (str(mock_zip_file.name), ANY, 'application/zip'))
        ]
    )


def test_deploy_success_kwarg_options(mock_sf_client, mock_zip_file):
    """Test successful execution of anonymous Apex code."""
    # Setup mock response for successful execution
    mock_response = Mock()
    mock_response.json.return_value = { "id" : "0Afxx00000001VPCAY",
      "deployOptions" :
       { "checkOnly" : False,
         "singlePackage" : False,
         "allowMissingFiles" : False,
         "performRetrieve" : False,
         "autoUpdatePackage" : False,
         "rollbackOnError" : True,
         "ignoreWarnings" : False,
         "purgeOnDelete" : False,
         "runAllTests" : False },
      "deployResult" :
       { "id" : "0Afxx00000001VPCAY",
         "success" : False,
         "checkOnly" : False,
         "ignoreWarnings" : False,
         "rollbackOnError" : True,
         "status" : "Pending",
         "runTestsEnabled" : False,
         "done" : False } }
    mock_sf_client.post.return_value = mock_response

    # Create Tooling instance with mock client
    tooling = MetadataResource(mock_sf_client)

    # Execute anonymous code
    result = tooling.request_deploy(
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
            ('json', (None, '{"deployOptions": {"singlePackage": true}}', 'application/json')),
            ('file', (str(mock_zip_file.name), ANY, 'application/zip'))
        ]
    )
