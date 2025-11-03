from asyncio import Task, sleep as sleep_async
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator
from time import sleep as sleep_sync
from typing import Any, Generic, Literal, TypeVar, TypedDict
from httpx import URL
from sf_toolkit.client import AsyncSalesforceClient, SalesforceClient
from typing_extensions import override

from ..logger import getLogger
from io import StringIO
import csv

from .fields import (
    CheckboxField,
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
_LOGGER = getLogger("bulk")

DELIMITER = Literal["BACKQUOTE", "CARET", "COMMA", "PIPE", "SEMICOLON", "TAB"]

DELIMITER_MAP: dict[DELIMITER, str] = {
    "BACKQUOTE": "`",
    "CARET": "^",
    "COMMA": ",",
    "PIPE": "|",
    "SEMICOLON": ";",
    "TAB": "\t",
}

COMPLETE_STATES = set(("JobComplete", "Aborted", "Failed"))


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
    columnDelimiter = PicklistField(options=list(DELIMITER_MAP.keys()))
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
        options=[
            "Open",
            "UploadComplete",
            "InProgress",
            "Aborted",
            "JobComplete",
            "Failed",
        ]
    )
    systemModstamp = DateTimeField()
    totalProcessingTime = IntField()

    _connection: str | None

    @classmethod
    def init_job(
        cls,
        sobject_type: str | type[SObject],
        operation: Literal["insert", "delete", "hardDelete", "update", "upsert"],
        column_delimiter: DELIMITER = "COMMA",
        line_ending: Literal["LF", "CRLF"] = "LF",
        external_id_field: str | None = None,
        connection: SalesforceClient | str | None = None,
        **callout_options: Any,
    ):
        if not isinstance(connection, SalesforceClient):
            connection = SalesforceClient.get_connection(connection)  # type: ignore

        assert isinstance(connection, SalesforceClient)

        payload = {
            "columnDelimiter": column_delimiter,
            "contentType": "CSV",
            "lineEnding": line_ending,
            "object": (
                sobject_type
                if isinstance(sobject_type, str)
                else sobject_type.attributes.type
            ),
            "operation": operation,
        }
        if operation == "upsert" and external_id_field:
            payload["externalIdFieldName"] = external_id_field
        url = connection.data_url + "/jobs/ingest"
        response = connection.post(url, json=payload, **callout_options)
        return cls(connection.connection_name, **response.json())

    @classmethod
    async def init_job_async(
        cls,
        sobject_type: str | type[SObject],
        operation: Literal["insert", "delete", "hardDelete", "update", "upsert"],
        column_delimiter: DELIMITER = "COMMA",
        line_ending: Literal["LF", "CRLF"] = "LF",
        external_id_field: str | None = None,
        connection: AsyncSalesforceClient | str | None = None,
        **callout_options: Any,
    ):
        if isinstance(connection, AsyncSalesforceClient):
            pass
        else:
            connection = AsyncSalesforceClient.get_connection(connection)  # type: ignore

        payload = {
            "columnDelimiter": column_delimiter,
            "contentType": "CSV",
            "lineEnding": line_ending,
            "object": (
                sobject_type
                if isinstance(sobject_type, str)
                else sobject_type.attributes.type
            ),
            "operation": operation,
        }
        if operation == "upsert" and external_id_field:
            payload["externalIdFieldName"] = external_id_field
        url = connection.data_url + "/jobs/ingest"
        response = await connection.post(url, json=payload, **callout_options)
        return cls(connection.connection_name, **response.json())

    @classmethod
    def upload_dataset(
        cls,
        dataset: SObjectList[_SO],
        poll_interval: float | int = 5,
        **callout_options,
    ):
        """
        Convenience method to create a Bulk API Ingest Job and upload the provided dataset.
        The dataset must be a non-empty SObjectList with a single SObject type.
        """
        if not dataset:
            raise ValueError("No data provided for upload_dataset")
        dataset.assert_single_type()
        job = cls.init_job(
            sobject_type=type(dataset[0]),
            operation="upsert",
            connection=dataset[0].attributes.connection,
            **callout_options,
        )
        _ = job.upload_batches(dataset, **callout_options)
        _ = job.monitor_until_complete(poll_interval, **callout_options)
        return job

    @classmethod
    async def upload_dataset_async(
        cls,
        dataset: SObjectList[_SO],
        poll_interval: int | float = 5,
        **callout_options,
    ):
        """
        Convenience method to create a Bulk API Ingest Job and upload the provided dataset.
        The dataset must be a non-empty SObjectList with a single SObject type.
        """
        if not dataset:
            raise ValueError("No data provided for upload_dataset")
        dataset.assert_single_type()
        job = await cls.init_job_async(
            sobject_type=type(dataset[0]),
            operation="upsert",
            connection=dataset[0].attributes.connection,
            **callout_options,
        )
        _ = await job.upload_batches_async(dataset, **callout_options)
        _ = await job.monitor_until_complete_async(poll_interval, **callout_options)
        return job

    def __init__(self, connection: str | None, **fields):
        self._connection = connection
        super().__init__(**fields)

    def _batch_buffers(self, data: SObjectList[_SO]):
        fieldnames = query_fields(type(data[0]))
        if self.operation == "delete" or self.operation == "hardDelete":
            fieldnames = ["Id"]
        if self.operation == "insert" and "Id" in fieldnames:
            fieldnames.remove("Id")
        line_terminator = "\n" if self.lineEnding == "LF" else "\r\n"
        with StringIO() as buffer:
            writer = csv.DictWriter(
                buffer,
                fieldnames,
                delimiter=self._delimiter_char(),
                lineterminator=line_terminator,
                extrasaction="ignore",
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
                    yield buffer.getvalue()
                    _ = buffer.seek(0)
                    _ = buffer.truncate()
                    writer.writeheader()
                    writer.writerow(serialized)
            yield buffer.getvalue()

    def upload_batches(self, data: SObjectList[_SO], **callout_options: Any):
        """
        Upload data batches to be processed by the Salesforce bulk API.
        https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/upload_job_data.htm
        """

        if not data:
            raise ValueError("No data provided for upload_batches")
        data.assert_single_type()
        _connection = SalesforceClient.get_connection(self._connection)
        for batch_buffer in self._batch_buffers(data):
            _ = _connection.put(
                self.contentUrl,
                content=batch_buffer,
                headers={
                    "Content-Type": "text/csv",
                    "Accept": "application/json",
                },
                **callout_options,
            )

        updated_values = _connection.patch(
            self.contentUrl.removesuffix("/batches"),
            json={"state": "UploadComplete"},
            **callout_options,
        ).json()
        for field, value in updated_values.items():
            setattr(self, field, value)
        return self

    async def upload_batches_async(
        self, data: SObjectList[_SO], **callout_options: Any
    ):
        """
        Upload data batches to be processed by the Salesforce bulk API.
        https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/upload_job_data.htm
        """

        if not data:
            raise ValueError("No data provided for upload_batches")
        data.assert_single_type()
        _connection = AsyncSalesforceClient.get_connection(self._connection)
        batch_count = 0
        for batch_content in self._batch_buffers(data):
            batch_count += 1
            _ = await _connection.put(
                self.contentUrl,
                content=batch_content,
                headers={
                    "Content-Type": "text/csv",
                    "Accept": "application/json",
                },
                **callout_options,
            )

        _LOGGER.debug("Uploaded %d batches", batch_count)

        updated_values = (
            await _connection.patch(
                self.contentUrl.removesuffix("/batches"),
                json={"state": "UploadComplete"},
                **callout_options,
            )
        ).json()
        for field, value in updated_values.items():
            setattr(self, field, value)
        return self

    def refresh(self, connection: SalesforceClient | str | None = None):
        if connection is None:
            connection = self._connection
        if not isinstance(connection, SalesforceClient):
            connection = SalesforceClient.get_connection(connection)  # type: ignore
            assert isinstance(connection, SalesforceClient), (
                "Could not find Salesforce Client connection"
            )
        response = connection.get(connection.data_url + f"/jobs/ingest/{self.id}")
        for key, value in response.json().items():
            setattr(self, key, value)
        return self

    async def refresh_async(
        self,
        connection: AsyncSalesforceClient | str | None = None,
    ):
        if connection is None:
            connection = self._connection
        if not isinstance(connection, AsyncSalesforceClient):
            connection = AsyncSalesforceClient.get_connection(connection)  # type: ignore
            assert isinstance(connection, AsyncSalesforceClient), (
                "Could not find Salesforce Client connection"
            )
        response = await connection.get(connection.data_url + f"/jobs/ingest/{self.id}")
        for key, value in response.json().items():
            setattr(self, key, value)
        return self

    def monitor_until_complete(
        self,
        poll_interval: float = 5.0,
        connection: SalesforceClient | str | None = None,
    ):
        _ = self.refresh(connection=connection)

        while self.state not in COMPLETE_STATES:
            _LOGGER.info(
                "Bulk %s job %s for object %s state: %s (%d processed, %d failed)",
                self.operation,
                self.id,
                self.object,
                self.state,
                self.numberRecordsProcessed,
                self.numberRecordsFailed,
            )
            sleep_sync(poll_interval)
            _ = self.refresh(connection=connection)
        return self

    async def monitor_until_complete_async(
        self,
        poll_interval: float = 5.0,
        connection: AsyncSalesforceClient | str | None = None,
    ):
        _ = await self.refresh_async(connection=connection)
        while self.state not in COMPLETE_STATES:
            _LOGGER.info(
                "Bulk %s job %s for object %s state: %s",
                self.operation,
                self.id,
                self.object,
                self.state,
            )
            await sleep_async(poll_interval)
            _ = self.refresh_async(connection=connection)
        return self

    def _delimiter_char(self) -> str:
        _cd: DELIMITER = self.columnDelimiter  # pyright: ignore[reportAssignmentType]
        return DELIMITER_MAP.get(_cd, ",")


class ResultPage(Generic[_SO]):
    """
    Represents a single Bulk API Query result page.
    Holds the locator resultUrl and provides helpers to fetch raw CSV and parsed rows.
    """

    _connection: str | None
    _column_delimiter: DELIMITER
    _url: URL
    _sobject_type: type[_SO]
    _line_ending: Literal["LF", "CRLF"]
    _records: SObjectList[_SO] | None = None
    _iter_index: int | None = None
    next_page_locator: str | None = None

    def __init__(
        self,
        connection: str | None,
        sobject_type: type[_SO],
        url: URL,
        column_delimiter: Literal[
            "BACKQUOTE", "CARET", "COMMA", "PIPE", "SEMICOLON", "TAB"
        ] = "COMMA",
        line_ending: Literal["LF", "CRLF"] = "LF",
    ):
        self._connection = connection
        self._url = url
        self._sobject_type = sobject_type
        self._column_delimiter = column_delimiter
        self._line_ending = line_ending

    def __next__(self):
        if self._records is None:
            self._records = self.fetch()
            self._iter_index = 0
        if self._iter_index is None:
            self._iter_index = 0
        try:
            return self._records[self._iter_index]
        except IndexError as e:
            self._iter_index = None
            raise StopIteration from e
        finally:
            if self._iter_index is not None:
                self._iter_index += 1

    async def __anext__(self):
        if self._records is None:
            self._records = await self.fetch_async()
            self._iter_index = 0
        if self._iter_index is None:
            self._iter_index = 0
        try:
            return self._records[self._iter_index]
        except IndexError as e:
            self._iter_index = None
            raise StopAsyncIteration from e
        finally:
            if self._iter_index is not None:
                self._iter_index += 1

    def __iter__(self):
        self._iter_index = 0
        return self

    async def __aiter__(self):
        self._iter_index = 0
        return self

    @property
    def records(self) -> SObjectList[_SO]:
        """
        Return all rows in this page as a SObjectList of the query's SObject type.
        Caches the result after the first call.
        """
        if self._records is None:
            return self.fetch()
        return self._records

    def fetch(self):
        """
        Fetch and parse the CSV payload for this result page (synchronous).
        """
        if self._records is not None:
            return self._records
        _connection = SalesforceClient.get_connection(self._connection)
        response = _connection.get(
            self._url,
            headers={
                "Accept": "text/csv",
                # Use compression!
                # https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/query_compression.htm
                "Accept-Encoding": "gzip",
            },
        )
        _ = response.raise_for_status()
        raw_csv = response.text
        delimiter_char = DELIMITER_MAP.get(self._column_delimiter, ",")
        line_terminator = "\n" if self._line_ending == "LF" else "\r\n"
        reader = csv.DictReader(
            StringIO(raw_csv),
            delimiter=delimiter_char,
            lineterminator=line_terminator,
        )
        rows = list(reader)
        self.next_page_locator = response.headers.get("Sforce-locator")
        if self.next_page_locator == "null":
            self.next_page_locator = None
        elif self.next_page_locator is not None:
            _LOGGER.info(
                "There's another page at locator "
                + self.next_page_locator
                + " :: "
                + str(self._url.copy_set_param("locator", self.next_page_locator))
            )
        self._records = SObjectList(
            self._sobject_type(**r)
            for r in rows  # type: ignore
        )
        breakpoint()
        return self._records

    async def fetch_async(self):
        """
        Fetch and parse the CSV payload for this result page (asynchronous).
        """
        async_conn = AsyncSalesforceClient.get_connection(self._connection)
        response = await async_conn.get(
            self._url,
            headers={
                "Accept": "text/csv",
                # Use compression!
                # https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/query_compression.htm
                "Accept-Encoding": "gzip",
            },
        )
        _ = response.raise_for_status()
        raw_csv = response.text
        delimiter_char = DELIMITER_MAP.get(self._column_delimiter, ",")
        line_terminator = "\n" if self._line_ending == "LF" else "\r\n"
        reader = csv.DictReader(
            StringIO(raw_csv),
            delimiter=delimiter_char,
            lineterminator=line_terminator,
        )
        rows = list(reader)
        self.next_page_locator = response.headers.get("Sforce-Locator") or None
        if self.next_page_locator == "null":
            self.next_page_locator = None
        if self.next_page_locator is not None:
            _LOGGER.info(
                "There's another page at locator "
                + self.next_page_locator
                + " :: "
                + str(self._url.copy_set_param("locator", self.next_page_locator))
            )
        self._records = SObjectList(
            self._sobject_type(**r)
            for r in rows  # type: ignore
        )
        return self._records

    def next_page(self) -> "ResultPage[_SO] | None":
        """
        Fetch the next result page if available (synchronous).
        """
        if not self.next_page_locator:
            return None
        next_page = ResultPage(
            connection=self._connection,
            sobject_type=self._sobject_type,
            url=self._url.copy_set_param("locator", self.next_page_locator),
            column_delimiter=self._column_delimiter,
        )
        _ = next_page.fetch()
        return next_page


class _ResultUrl(TypedDict):
    resultUrl: str


class _QueryPagesResponse(TypedDict):
    resultPages: list[_ResultUrl]
    nextRecordsUrl: str | None
    done: bool


class BulkQueryResult(
    Iterator[_SO], AsyncIterator[_SO], Iterable[_SO], AsyncIterable[_SO]
):
    pages: list[ResultPage[_SO]]
    _connection: str | None
    _job_id: str
    _sobject_type: type[_SO]
    _record_index: int = 0
    _page_index: int = 0
    _async_tasks: list[Task[None]] = []
    _column_delimiter: DELIMITER
    _line_ending: Literal["LF", "CRLF"] = "LF"

    def __init__(
        self,
        connection: str | None,
        sobject_type: type[_SO],
        job_id: str,
        pages: list[ResultPage[_SO]],
        column_delimiter: DELIMITER = "COMMA",
        line_ending: Literal["LF", "CRLF"] = "LF",
    ):
        self._connection = connection
        self._sobject_type = sobject_type
        self.pages = pages
        self._column_delimiter = column_delimiter
        self._line_ending = line_ending
        self._job_id = job_id
        try:
            _connection = SalesforceClient.get_connection(self._connection)
        except KeyError:
            _connection = AsyncSalesforceClient.get_connection(self._connection)
        self.url = URL(
            raw_path=(
                _connection.data_url + f"/jobs/query/{self._job_id}/results"
            ).encode("utf-8")
        )

    def copy(self) -> "BulkQueryResult[_SO]":
        return BulkQueryResult(
            connection=self._connection,
            sobject_type=self._sobject_type,
            job_id=self._job_id,
            pages=self.pages,
            column_delimiter=self._column_delimiter,
            line_ending=self._line_ending,
        )

    @override
    def __iter__(self) -> Iterator[_SO]:
        return self.copy()

    @override
    def __aiter__(self) -> AsyncIterator[_SO]:
        return self.copy()

    @property
    def done(self) -> bool:
        return self.pages[-1].next_page_locator is None

    def as_list(self) -> SObjectList[_SO]:
        """
        Return all rows in all pages as a SObjectList of the query's SObject type.
        Caches the result after the first call.
        """
        return SObjectList(self, connection=self._connection)

    async def as_list_async(self) -> SObjectList[_SO]:
        """
        Return all rows in all pages as a SObjectList of the query's SObject type.
        Caches the result after the first call.
        """
        return await SObjectList.async_init(self, connection=self._connection)

    async def _fetch_page(self, locator: str) -> ResultPage[_SO]:
        page = ResultPage(
            connection=self._connection,
            sobject_type=self._sobject_type,
            url=self.url.copy_set_param("locator", locator),
            column_delimiter=self._column_delimiter,
        )
        _ = await page.fetch_async()
        return page

    @override
    def __next__(self) -> _SO:
        try:
            return next(self.pages[self._page_index])
        except StopIteration:
            # Page finished, Move to the next page
            self._page_index += 1
            if self._page_index >= len(self.pages):
                # No more pages loaded, try to fetch more
                _next_page = self.pages[-1].next_page()
                if _next_page is not None:
                    self.pages.append(_next_page)
                else:
                    raise StopIteration

            return next(self.pages[self._page_index])

    @override
    async def __anext__(self) -> _SO:
        try:
            return await anext(self.pages[self._page_index])
        except StopIteration:
            # Page finished, Move to the next page
            self._page_index += 1
            if self._page_index >= len(self.pages):
                # No more pages loaded, try to fetch more
                if _next_page := self.pages[-1].next_page():
                    self.pages.append(_next_page)
                else:
                    raise StopIteration

            return await anext(self.pages[self._page_index])


class BulkApiQueryJob(FieldConfigurableObject, Generic[_SO]):
    """
    Represents a Salesforce Bulk API 2.0 query job with its properties and state.
    https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/query_create_job.htm
    """

    id: IdField = IdField()
    operation: PicklistField = PicklistField(options=["query", "queryAll"])
    object: TextField = TextField()
    createdById: IdField = IdField()
    createdDate: DateTimeField = DateTimeField()
    systemModstamp: DateTimeField = DateTimeField()
    state: PicklistField = PicklistField(
        options=[
            "Open",
            "UploadComplete",
            "InProgress",
            "Aborted",
            "JobComplete",
            "Failed",
        ]
    )
    concurrencyMode: TextField = (
        TextField()
    )  # Reserved for future use. Currently only parallel mode is supported.
    contentType: PicklistField = PicklistField(options=["CSV"])
    apiVersion: NumberField = NumberField()
    jobType: PicklistField = PicklistField(options=["V2Query"])
    lineEnding: PicklistField = PicklistField(options=["LF", "CRLF"])
    columnDelimiter: PicklistField = PicklistField(
        options=["BACKQUOTE", "CARET", "COMMA", "PIPE", "SEMICOLON", "TAB"]
    )
    numberRecordsProcessed: IntField = IntField()
    retries: IntField = IntField()
    totalProcessingTime: IntField = IntField()
    isPkChunkingSupported: CheckboxField = CheckboxField()

    _connection: str | None
    _sobject: type[SObject]
    result: BulkQueryResult[_SO]

    @classmethod
    def init_job(
        cls,
        query: "SoqlQuery[_SO]",
        connection: SalesforceClient | str | None = None,
        operation: Literal["query", "queryAll"] = "query",
        column_delimiter: Literal[
            "BACKQUOTE", "CARET", "COMMA", "PIPE", "SEMICOLON", "TAB"
        ] = "COMMA",
        line_ending: Literal["LF", "CRLF"] = "LF",
        **callout_options,
    ):
        global SoqlQuery
        try:
            _ = SoqlQuery
        except NameError:
            from sf_toolkit.data.query_builder import SoqlQuery
        if not isinstance(connection, SalesforceClient):
            connection = SalesforceClient.get_connection(connection)  # type: ignore

        assert isinstance(connection, SalesforceClient)

        payload = {
            "operation": operation,
            "query": query.format(),
            "columnDelimiter": column_delimiter,
            "lineEnding": line_ending,
        }
        url = connection.data_url + "/jobs/query"
        response = connection.post(url, json=payload, **callout_options)
        return cls(connection.connection_name, query.sobject_type, **response.json())

    @classmethod
    async def init_job_async(
        cls,
        query: "SoqlQuery[_SO]",
        connection: AsyncSalesforceClient | str | None = None,
        operation: Literal["query", "queryAll"] = "query",
        column_delimiter: Literal[
            "BACKQUOTE", "CARET", "COMMA", "PIPE", "SEMICOLON", "TAB"
        ] = "COMMA",
        line_ending: Literal["LF", "CRLF"] = "LF",
        **callout_options,
    ):
        global SoqlQuery
        try:
            _ = SoqlQuery
        except NameError:
            from sf_toolkit.data.query_builder import SoqlQuery
        if isinstance(connection, AsyncSalesforceClient):
            pass
        else:
            connection = AsyncSalesforceClient.get_connection(connection)  # type: ignore

        payload = {
            "operation": operation,
            "query": query.format(),
            "columnDelimiter": column_delimiter,
            "lineEnding": line_ending,
        }
        url = connection.data_url + "/jobs/query"
        response = await connection.post(url, json=payload, **callout_options)
        _ = response.raise_for_status()
        return cls(connection.connection_name, query.sobject_type, **response.json())

    def __init__(self, connection: str | None, sobject_type: type[_SO], **fields):
        self._connection = connection
        try:
            _connection = SalesforceClient.get_connection(self._connection)
        except KeyError:
            _connection = AsyncSalesforceClient.get_connection(self._connection)
        self._sobject = sobject_type
        super().__init__(**fields)
        self.result = BulkQueryResult(
            connection=self._connection,
            sobject_type=self._sobject,
            job_id=self.id,
            pages=[
                ResultPage(
                    connection=self._connection,
                    sobject_type=self._sobject,
                    url=URL(
                        raw_path=(
                            _connection.data_url + f"/jobs/query/{self.id}/results"
                        ).encode()
                    ),
                    column_delimiter=self.columnDelimiter,  # pyright: ignore[reportArgumentType]
                )
            ],
            column_delimiter=self.columnDelimiter,  # pyright: ignore[reportArgumentType]
            line_ending=self.lineEnding,  # pyright: ignore[reportArgumentType]
        )

    def __iter__(self):
        return self.result.__iter__()

    def __aiter__(self):
        return self.result.__aiter__()

    def monitor_until_complete(
        self,
        poll_interval: float = 5.0,
        connection: SalesforceClient | str | None = None,
    ):
        _ = self.refresh(connection=connection)

        while self.state not in COMPLETE_STATES:
            _LOGGER.info(
                "Bulk %s job %s for object %s state: %s",
                self.operation,
                self.id,
                self.object,
                self.state,
            )
            sleep_sync(poll_interval)
            _ = self.refresh(connection=connection)
        return self

    async def monitor_until_complete_async(
        self,
        poll_interval: float = 5.0,
        connection: AsyncSalesforceClient | str | None = None,
    ):
        _ = await self.refresh_async(connection=connection)
        while self.state not in COMPLETE_STATES:
            _LOGGER.info(
                "Bulk %s job %s for object %s state: %s",
                self.operation,
                self.id,
                self.object,
                self.state,
            )
            await sleep_async(poll_interval)
            _ = await self.refresh_async(connection=connection)
        return self

    def refresh(self, connection: SalesforceClient | str | None = None):
        if connection is None:
            connection = self._connection
        if not isinstance(connection, SalesforceClient):
            connection = SalesforceClient.get_connection(connection)  # type: ignore
            assert isinstance(connection, SalesforceClient), (
                "Could not find Salesforce Client connection"
            )
        response = connection.get(connection.data_url + f"/jobs/query/{self.id}")
        for key, value in response.json().items():
            setattr(self, key, value)
        return self

    async def refresh_async(
        self,
        connection: AsyncSalesforceClient | str | None = None,
    ):
        if not connection:
            connection = self._connection
        if not isinstance(connection, AsyncSalesforceClient):
            connection = AsyncSalesforceClient.get_connection(connection)
        assert isinstance(connection, AsyncSalesforceClient), (
            "Could not find Salesforce Client connection"
        )
        response = await connection.get(connection.data_url + f"/jobs/query/{self.id}")
        for key, value in response.json().items():
            setattr(self, key, value)
        return self
