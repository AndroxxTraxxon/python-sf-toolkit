from typing import Literal, TypeVar
from io import StringIO
import csv

from ..interfaces import I_SalesforceClient
from . import fields
from .transformers import flatten

from .sobject import SObject, SObjectList

T = TypeVar("T")
_SO = TypeVar("_SO", bound=SObject)


class BulkApiIngestJob(fields.FieldConfigurableObject):
    """
    Represents a Salesforce Bulk API 2.0 job with its properties and state.
    https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/get_all_jobs.htm
    """

    # Attribute type annotations
    apexProcessingTime = fields.IntField()
    apiActiveProcessingTime = fields.IntField()
    apiVersion = fields.TextField()
    assignmentRuleId = fields.IdField()
    columnDelimiter = fields.PicklistField(
        options=["BACKQUOTE", "CARET", "COMMA", "PIPE", "SEMICOLON", "TAB"]
    )
    concurrencyMode = (
        fields.TextField()
    )  # This should be an enum, but I can't find the spec.
    contentType = fields.PicklistField(options=["CSV"])
    contentUrl = fields.TextField()
    createdById = fields.IdField()
    createdDate = fields.DateTimeField()
    errorMessage = fields.TextField()
    externalIdField = fields.TextField()
    id = fields.IdField()
    jobType = fields.PicklistField(options=["BigObjectIngest", "Classic", "V2Ingest"])
    lineEnding = fields.PicklistField(options=["LF", "CRLF"])
    numberRecordsFailed = fields.IntField()
    numberRecordsProcessed = fields.IntField()
    object = fields.TextField()
    operation = fields.PicklistField(
        options=[
            "insert",
            "delete",
            "hardDelete",
            "update",
            "upsert",
        ]
    )
    retries = fields.IntField()
    state = fields.PicklistField(
        options=["Open", "UploadComplete", "Aborted", "JobComplete", "Failed"]
    )
    systemModstamp = fields.DateTimeField()
    totalProcessingTime = fields.IntField()

    @classmethod
    def init_job(
        cls,
        sobject_type: str,
        operation: Literal["insert", "delete", "hardDelete", "update", "upsert"],
        column_delimiter: Literal[
            "BACKQUOTE", "CARET", "COMMA", "PIPE", "SEMICOLON", "TAB"
        ] = "COMMA",
        line_ending: Literal["LF", "CRLF"] = "LF",
        external_id_field: str | None = None,
        connection: I_SalesforceClient | str | None = None,
        **callout_options,
    ):
        if not isinstance(connection, I_SalesforceClient):
            connection = I_SalesforceClient.get_connection(connection)  # type: ignore

        assert isinstance(connection, I_SalesforceClient)

        payload = {
            "columnDelimiter": column_delimiter,
            "contentType": "CSV",
            "lineEnding": line_ending,
            "object": sobject_type,
            "operation": operation,
        }
        if operation == "upsert" and external_id_field:
            payload["externalIdFieldName"] = external_id_field
        url = connection.data_url + "/jobs/ingest"
        response = connection.post(url, json=payload, **callout_options)
        return cls(**response.json())

    def __init__(self, connection: I_SalesforceClient, **fields):
        self._connection = connection
        super().__init__(**fields)

    def upload_batches(self, data: SObjectList[_SO], **callout_options):
        """
        Upload data batches to be processed by the Salesforce bulk API.
        https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/upload_job_data.htm
        """

        assert data, "Cannot upload an empty list"
        data.assert_single_type()
        fieldnames = fields.query_fields(type(data[0]))
        with StringIO() as buffer:
            writer = csv.DictWriter(
                buffer, fieldnames, delimiter=self._delimiter_char()
            )
            writer.writeheader()
            buffer_has_data = False
            for row in data:
                serialized = flatten(fields.serialize_object(row))
                writer.writerow(serialized)
                buffer_has_data = True
                if buffer.tell() > 100_000_000:
                    # https://resources.docs.salesforce.com/256/latest/en-us/sfdc/pdf/api_asynch.pdf
                    # > A request can provide CSV data that does not in total exceed 150 MB
                    # > of base64 encoded content. When job data is uploaded, it is
                    # > converted to base64. This conversion can increase the data size by
                    # > approximately 50%. To account for the base64 conversion increase,
                    # > upload data that does not exceed 100 MB.
                    _ = buffer.seek(0)
                    _ = self._connection.put(
                        self.contentUrl,
                        files=[("content", ("content", buffer.getvalue(), "text/csv"))],
                        **callout_options,
                    )
                    _ = buffer.seek(0)
                    _ = buffer.truncate()
                    writer.writeheader()
                    buffer_has_data = False
            if buffer_has_data:
                self._connection.put(
                    self.contentUrl,
                    files=[("content", ("content", buffer.getvalue(), "text/csv"))],
                    **callout_options,
                )

            updated_values = self._connection.patch(
                self.contentUrl.removesuffix("/batches"),
                json={"state": "UploadComplete"},
                **callout_options,
            ).json()
            for field, value in updated_values.items():
                setattr(self, field, value)
            return self

    def refresh(self, connection: I_SalesforceClient | str | None = None):
        if connection is None:
            connection = self._connection
        if not isinstance(connection, I_SalesforceClient):
            connection = I_SalesforceClient.get_connection(connection)  # type: ignore
        assert isinstance(connection, I_SalesforceClient), (
            "Could not find Salesforce Client connection"
        )
        response = connection.get(connection.data_url + f"/jobs/ingest/{self.id}")
        for key, value in response.json().items():
            setattr(self, key, value)
        return self

    def _delimiter_char(self) -> str:
        return {
            "BACKQUOTE": "`",
            "CARET": "^",
            "COMMA": ",",
            "PIPE": "|",
            "SEMICOLON": ";",
            "TAB": "\t",
        }.get(self.columnDelimiter, ",")
