from typing import Literal, TypeVar
from io import StringIO
import csv

from ..interfaces import I_SalesforceClient
from .fields import (
    FieldConfigurableObject,
    IntField,
    IdField,
    NumberField,
    PicklistField,
    TextField,
    DateTimeField,
    query_fields,
    serialize_object,
)
from .transformers import flatten

from .sobject import SObject, SObjectList

T = TypeVar("T")
_SO = TypeVar("_SO", bound=SObject)


class BulkApiIngestJob(FieldConfigurableObject):
    """
    Represents a Salesforce Bulk API 2.0 job with its properties and state.
    https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/get_all_jobs.htm
    """

    # Attribute type annotations
    apexProcessingTime = IntField()
    apiActiveProcessingTime = IntField()
    apiVersion = NumberField()
    assignmentRuleId = IdField()
    columnDelimiter = PicklistField(
        options=["BACKQUOTE", "CARET", "COMMA", "PIPE", "SEMICOLON", "TAB"]
    )
    concurrencyMode = TextField()  # This should be an enum, but I can't find the spec.
    contentType = PicklistField(options=["CSV"])
    contentUrl = TextField()
    createdById = IdField()
    createdDate = DateTimeField()
    errorMessage = TextField()
    externalIdField = TextField()
    id = IdField()
    jobType = PicklistField(options=["BigObjectIngest", "Classic", "V2Ingest"])
    lineEnding = PicklistField(options=["LF", "CRLF"])
    numberRecordsFailed = IntField()
    numberRecordsProcessed = IntField()
    object = TextField()
    operation = PicklistField(
        options=[
            "insert",
            "delete",
            "hardDelete",
            "update",
            "upsert",
        ]
    )
    retries = IntField()
    state = PicklistField(
        options=["Open", "UploadComplete", "Aborted", "JobComplete", "Failed"]
    )
    systemModstamp = DateTimeField()
    totalProcessingTime = IntField()

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
        return cls(connection, **response.json())

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
        fieldnames = query_fields(type(data[0]))
        if self.operation == "delete" or self.operation == "hardDelete":
            fieldnames = ["Id"]
        line_terminator = "\n" if self.lineEnding == "LF" else "\r\n"
        with StringIO() as buffer:
            writer = csv.DictWriter(
                buffer,
                fieldnames,
                delimiter=self._delimiter_char(),
                lineterminator=line_terminator,
            )
            writer.writeheader()
            for row in data:
                before_row_len = buffer.tell()
                if self.operation == "delete" or self.operation == "hardDelete":
                    serialized = {"Id": row["Id"]}
                else:
                    serialized = flatten(serialize_object(row))
                writer.writerow(serialized)
                if buffer.tell() > 100_000_000:
                    # https://resources.docs.salesforce.com/256/latest/en-us/sfdc/pdf/api_asynch.pdf
                    # > A request can provide CSV data that does not in total exceed 150 MB
                    # > of base64 encoded content. When job data is uploaded, it is
                    # > converted to base64. This conversion can increase the data size by
                    # > approximately 50%. To account for the base64 conversion increase,
                    # > upload data that does not exceed 100 MB.

                    # rewind to the row before the limit was exceeded
                    _ = buffer.seek(before_row_len)
                    _ = buffer.truncate()
                    # push batch with data up to the previous row
                    _ = self._connection.put(
                        self.contentUrl,
                        content=buffer.getvalue(),
                        headers={
                            "Content-Type": "text/csv",
                            "Accept": "application/json",
                        },
                        **callout_options,
                    )
                    # reset buffer and write the current row again
                    _ = buffer.seek(0)
                    _ = buffer.truncate()
                    writer.writeheader()
                    writer.writerow(serialized)
            _ = self._connection.put(
                self.contentUrl,
                content=buffer.getvalue() + "\n",
                headers={"Content-Type": "text/csv", "Accept": "application/json"},
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
