.. contents::
   :local:
   :depth: 2

SF Toolkit Metadata API Resources
---------------------------------

SF Toolkit provides several Python classes and functions to interact with Salesforce Metadata API. These resources enable you to deploy metadata, manage deployment options, handle deployment statuses, and more.

DeployRequest
^^^^^^^^^^^^^

The `DeployRequest` class allows managing the status of a deployment request, canceling deployment, or quick deploying validated components.

**Methods**

- ``current_status(self, include_details: bool = True, connection: I_SalesforceClient | str | None = None) -> "DeployRequest"``
  Retrieves the current status of a deployment request. Optionally includes detailed deployment results.

- ``cancel(self, connection: I_SalesforceClient | str | None = None) -> "DeployRequest"``
  Attempts to cancel the ongoing deployment request. Returns the updated deployment request status.

- ``quick_deploy_validated(self, connection: I_SalesforceClient | str | None = None) -> "DeployRequest"``
  Initiates a quick deployment using a previously validated deployment request without further tests.

DeployOptions
^^^^^^^^^^^^^

The `DeployOptions` class specifies the various configuration options available for a deployment. These options include flag settings such as `allowMissingFiles`, `checkOnly`, `ignoreWarnings`, and many others configured at initiation.

DeployResult and DeployDetails
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

`DeployResult` and `DeployDetails` classes store and manage the results of a deployment operation, providing access to the statuses, counts of successes and failures, and individual component statuses derived from the deployment process.

RetrieveResult
^^^^^^^^^^^^^

Leverage the `RetrieveResult` class to handle results from retrieve operations, which contain metadata file properties, the retrieve status, and messages related to the process.

RunTestsResult
^^^^^^^^^^^^^^

Use the `RunTestsResult` class to manage results from running tests as part of the deployment. This includes test successes, failures, and code coverage details.

CodeCoverageResult and CodeCoverageWarning
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

These classes provide interfaces to manage and retrieve information about code coverage following Apex tests, including uncovered code locations and coverage-related warnings.

Metadata Resource
^^^^^^^^^^^^^^^^^

The `MetadataResource` class exposes methods like `deploy` which allow for deploying ZIP archives via the Metadata API using a set of given deployment options.

**Example Usage**

.. code-block:: python

    # Instantiate your client
    client = SalesforceClient(...)

    # Path to your ZIP file containing metadata
    archive_path = Path('path/to/metadata.zip')

    # Initiating a deployment request
    deploy_request = client.metadata.deploy(
        archive_path,
        checkOnly=False,
        ignoreWarnings=True
    )

    # Alternatively, initiating a deployment request with explicit deploy options
    # This example achieves the same deploy request.
    deploy_options = DeployOptions(checkOnly=False, ignoreWarnings=True)
    deploy_request = client.metadata.deploy(archive_path, deploy_options)

    # Checking the status of a deployment request
    updated_deploy_request = deploy_request.current_status()
    print(updated_deploy_request.deployResult.status)

    # Canceling a deployment request
    deploy_request.cancel()

**References**


For more information, consult the Salesforce Metadata API documentation linked within the methods described.
