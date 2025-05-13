import json
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, Unpack


from sf_toolkit.interfaces import I_SalesforceClient
from .base import ApiResource
from ..data import fields


class DeployMessage(fields.FieldConfigurableObject):
    """
    https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_deployresult.htm#deploymessage
    """

    changed = fields.CheckboxField()
    columnNumber = fields.IntField()
    componentType = fields.TextField()
    created = fields.CheckboxField()
    createdDate = fields.DateTimeField()
    deleted = fields.CheckboxField()
    fileName = fields.TextField()
    fullName = fields.TextField()
    id = fields.IdField()
    problem = fields.TextField()
    problemType = fields.PicklistField(options=["Warning", "Error"])
    success = fields.CheckboxField()


class FileProperties(fields.FieldConfigurableObject):
    createdById = fields.IdField()
    createdByName = fields.TextField()
    createdDate = fields.DateTimeField()
    fileName = fields.TextField()
    fullName = fields.TextField()
    id = fields.IdField()
    lastModifiedById = fields.IdField()
    lastModifiedByName = fields.TextField()
    lastModifiedDate = fields.DateTimeField()
    manageableState = fields.PicklistField(
        options=[
            "beta",
            "deleted",
            "deprecated",
            "deprecatedEditable",
            "installed",
            "installedEditable",
            "released",
            "unmanaged",
        ]
    )
    namespacePrefix = fields.TextField()
    type = fields.TextField()


class RetrieveMessage(fields.FieldConfigurableObject):
    fileName = fields.TextField()
    problem = fields.TextField()


class RetrieveResult(fields.FieldConfigurableObject):
    done = fields.CheckboxField()
    errorMessage = fields.TextField()
    errorStatusCode = fields.TextField()
    fileProperties = fields.ListField(FileProperties)
    id = fields.IdField()
    message = fields.ListField(RetrieveMessage)
    status = fields.PicklistField(
        options=["Pending", "InProgress", "Succeeded", "Failed"]
    )
    zipFile = fields.BlobField()


class CodeLocation(fields.FieldConfigurableObject):
    column = fields.IntField()
    line = fields.IntField()
    numExecutions = fields.IntField()
    time = fields.NumberField()


class CodeCoverageResult(fields.FieldConfigurableObject):
    dmlInfo = fields.ListField(CodeLocation)
    id = fields.IdField()
    locationsNotCovered = fields.ListField(CodeLocation)
    methodInfo = fields.ListField(CodeLocation)
    name = fields.TextField()
    namespace = fields.TextField()
    numLocations = fields.IntField()
    soqlInfo = fields.ListField(CodeLocation)


class CodeCoverageWarning(fields.FieldConfigurableObject):
    id = fields.IdField()
    message = fields.TextField()
    name = fields.TextField()
    namespace = fields.TextField()


class RunTestSuccess(fields.FieldConfigurableObject):
    id = fields.IdField()
    methodName = fields.TextField()
    name = fields.TextField()
    namespace = fields.TextField()
    seeAllData = fields.CheckboxField()
    time = fields.NumberField()


class RunTestFailure(fields.FieldConfigurableObject):
    id = fields.IdField()
    message = fields.TextField()
    methodName = fields.TextField()
    name = fields.TextField()
    namespace = fields.TextField()
    seeAllData = fields.CheckboxField()
    stackTrace = fields.TextField()
    time = fields.NumberField()
    type = fields.TextField()


class FlowCoverageResult(fields.FieldConfigurableObject):
    elementsNotCovered = fields.TextField()
    flowId = fields.TextField()
    flowName = fields.TextField()
    flowNamespace = fields.TextField()
    numElements = fields.IntField()
    numElementsNotCovered = fields.IntField()
    processType = fields.TextField()


class FlowCoverageWarning(fields.FieldConfigurableObject):
    flowId = fields.TextField()
    flowName = fields.TextField()
    flowNamespace = fields.TextField()
    message = fields.TextField()


class RunTestsResult(fields.FieldConfigurableObject):
    apexLogId = fields.IdField()
    codeCoverage = fields.ListField(CodeCoverageResult)
    codeCoverageWarnings = fields.ListField(CodeCoverageWarning)
    successes = fields.ListField(RunTestSuccess)
    failures = fields.ListField(RunTestFailure)
    numFailures = fields.IntField()
    numTestsRun = fields.IntField()
    totalTime = fields.NumberField()


class DeployDetails(fields.FieldConfigurableObject):
    componentFailures = fields.ListField(DeployMessage)
    componentSuccesses = fields.ListField(DeployMessage)
    retrieveResult = fields.ReferenceField(RetrieveResult)
    runTestResult = fields.ReferenceField(RunTestsResult)


class DeployResult(fields.FieldConfigurableObject):
    id = fields.IdField()
    canceledBy = fields.IdField()
    canceledByName = fields.TextField()
    checkOnly = fields.CheckboxField()
    completedDate = fields.DateTimeField()
    createdBy = fields.IdField()
    createdByName = fields.TextField()
    createdDate = fields.DateTimeField()
    details = fields.ReferenceField(DeployDetails)
    done = fields.CheckboxField()
    errorMessage = fields.TextField()
    errorStatusCode = fields.TextField()
    ignoreWarnings = fields.CheckboxField()
    lastModifiedDate = fields.DateTimeField()
    numberComponentErrors = fields.IntField()
    numberComponentsDeployed = fields.IntField()
    numberComponentsTotal = fields.IntField()
    numberTestErrors = fields.IntField()
    numberTestsCompleted = fields.IntField()
    numberTestsTotal = fields.IntField()
    runTestsEnabled = fields.CheckboxField()
    rollbackOnError = fields.CheckboxField()
    startDate = fields.DateTimeField()
    stateDetail = fields.TextField()
    status = fields.PicklistField(
        options=[
            "Pending",
            "InProgress",
            "Succeeded",
            "SucceededPartial",
            "Failed",
            "Canceling",
            "Canceled",
        ]
    )
    success = fields.CheckboxField()


class DeployOptionsDict(TypedDict):
    allowMissingFiles: NotRequired[bool]
    checkOnly: NotRequired[bool]
    ignoreWarnings: NotRequired[bool]
    purgeOnDelete: NotRequired[bool]
    rollbackOnError: NotRequired[bool]
    runTests: NotRequired[list[str]]
    singlePackage: NotRequired[bool]
    testLevel: NotRequired[
        Literal["NoTestRun", "RunSpecifiedTests", "RunLocalTests", "RunAllTestsInOrg"]
    ]


class DeployOptions(fields.FieldConfigurableObject):
    """
    Salesforce Deployment Options parameters:

    allowMissingFiles: bool
    autoUpdatePackage: bool
    checkOnly: bool
    ignoreWarnings: bool
    performRetrieve: bool
    purgeOnDelete: bool
    rollbackOnError: bool
    runAllTests: bool
    runTests: list[str]
    singlePackage: bool
    testLevel: Literal["NoTestRun", "RunSpecifiedTests", "RunLocalTests", "RunAllTestsInOrg"]

    "https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_rest_deploy.htm"
    """

    allowMissingFiles = fields.CheckboxField()
    autoUpdatePackage = fields.CheckboxField()
    checkOnly = fields.CheckboxField()
    ignoreWarnings = fields.CheckboxField()
    performRetrieve = fields.CheckboxField()
    purgeOnDelete = fields.CheckboxField()
    rollbackOnError = fields.CheckboxField()
    runAllTests = fields.CheckboxField()
    runTests = fields.ListField(str)  # type: ignore
    singlePackage = fields.CheckboxField()
    testLevel = fields.PicklistField(
        options=["NoTestRun", "RunSpecifiedTests", "RunLocalTests", "RunAllTestsInOrg"]
    )


class DeployRequest(fields.FieldConfigurableObject):
    """
    Deploy Metadata with Apex Testing Using REST
    https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_rest_deploy.htm
    """

    id = fields.IdField()
    validatedDeployRequestId = fields.IdField()
    url = fields.TextField()
    deployResult = fields.ReferenceField(DeployResult)
    deployOptions = fields.ReferenceField(DeployOptions)

    def __init__(self, _connection: I_SalesforceClient | None = None, **fields):
        super().__init__(**fields)
        self._connection = _connection

    def current_status(
        self,
        include_details: bool = True,
        connection: I_SalesforceClient | str | None = None,
    ) -> "DeployRequest":
        """
        Get the current status of a deployment request
        https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_rest_deploy_checkstatus.htm
        """
        if connection is None and self._connection:
            connection = self._connection
        if not isinstance(connection, I_SalesforceClient):
            connection = I_SalesforceClient.get_connection(connection)
        url = self.url or f"{connection.metadata_url}/deployRequest/{self.id}"
        params = {"includeDetails": True} if include_details else {}
        response = connection.get(url, params=params)
        return type(self)(_connection=connection, **response.json())

    def cancel(
        self, connection: I_SalesforceClient | str | None = None
    ) -> "DeployRequest":
        """
        Cancel the deployment request
        https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_rest_deploy_cancel.htm
        """
        if connection is None and self._connection:
            connection = self._connection
        if not isinstance(connection, I_SalesforceClient):
            connection = I_SalesforceClient.get_connection(connection)
        url = self.url or f"{connection.metadata_url}/deployRequest/{self.id}"
        response = connection.patch(url, json={"deployResult": {"status": "Canceling"}})
        if response.status_code != 202:
            raise ValueError("Deployment Failed to cancel")
        return type(self)(_connection=connection, **response.json())

    def quick_deploy_validated(
        self, connection: I_SalesforceClient | str | None = None
    ) -> "DeployRequest":
        """
        Deploy a Recently Validated Component Set Without Tests
        https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_rest_deploy_recentvalidation.htm
        """
        assert self.deployOptions.checkOnly, (
            "Original deployOptions.checkOnly needs to have been true to quick deploy."
        )
        if connection is None and self._connection:
            connection = self._connection
        if not isinstance(connection, I_SalesforceClient):
            connection = I_SalesforceClient.get_connection(connection)
        url = self.url or f"{connection.metadata_url}/deployRequest/{self.id}"
        response = connection.post(url, json={"validatedDeployRequestId": self.id})
        return type(self)(_connection=connection, **response.json())


class MetadataResource(ApiResource):
    def deploy(
        self,
        archive_path: Path,
        deploy_options: DeployOptions | None = None,
        **kwargs: Unpack[DeployOptionsDict],
    ) -> DeployRequest:
        """
        Request a deployment via the Metadata REST API
        https://developer.salesforce.com/docs/atlas.en-us.api_meta.meta/api_meta/meta_rest_deploy.htm
        """
        if deploy_options is None:
            assert kwargs, (
                "Must provide either deploy_options or deploy options as kwargs"
            )
            deploy_options = DeployOptions(**kwargs)
        else:
            assert not kwargs, "deploy_options cannot be provided with other kwargs"
        assert isinstance(archive_path, Path), (
            "archive_path must be an instance of pathlib.Path"
        )
        assert archive_path.suffix.casefold() == ".zip", "Must be a .zip archive"
        response = None
        with archive_path.open("rb") as archive_file:
            response = self.client.post(
                self.client.metadata_url + "/deployRequest",
                files=[
                    (
                        "json",
                        (
                            None,
                            json.dumps(
                                DeployRequest(deployOptions=deploy_options).serialize()
                            ),
                            "application/json",
                        ),
                    ),
                    ("file", (archive_path.name, archive_file, "application/zip")),
                ],
            )
        assert response is not None, "Did not receive response for Deploy Request."
        return DeployRequest(_connection=self.client, **response.json())
