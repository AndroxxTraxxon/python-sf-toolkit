from abc import ABC
import asyncio
from contextlib import ExitStack
import json
from pathlib import Path
from typing import Any, NamedTuple, TypeVar
from collections.abc import Iterable, AsyncIterable

import warnings
from ..logger import getLogger

from .. import client as sftk_client

from .transformers import chunked
from ..async_utils import run_concurrently
from .._models import SObjectAttributes, SObjectSaveResult
from ..interfaces import I_AsyncSalesforceClient, I_SObject, I_SalesforceClient
from . import fields
from .fields import (
    BlobData,
    BlobField,
    FieldConfigurableObject,
    dirty_fields,
    object_fields,
    query_fields,
    serialize_object,
)
from .transformers import flatten

_logger = getLogger("sobject")
_sObject = TypeVar("_sObject", bound="SObject")

_T = TypeVar("_T")


class SObjectFieldDescribe(NamedTuple):
    """Represents metadata about a Salesforce SObject field"""

    name: str = ""
    label: str = ""
    type: str = ""
    length: int = 0
    nillable: bool = True
    picklistValues: list[str] = []
    referenceTo: list[str] = []
    relationshipName: str = ""
    unique: bool = False
    updateable: bool = True
    createable: bool = True
    defaultValue: Any = None
    externalId: bool = False
    autoNumber: bool = False
    calculated: bool = False
    caseSensitive: bool = False
    dependentPicklist: bool = False
    deprecatedAndHidden: bool = False
    displayLocationInDecimal: bool = False
    filterable: bool = True
    groupable: bool = False
    permissionable: bool = False
    restrictedPicklist: bool = False
    sortable: bool = True
    writeRequiresMasterRead: bool = False


class SObjectDescribe:
    """Represents metadata about a Salesforce SObject from a describe call"""

    def __init__(
        self,
        *,
        name: str = "",
        label: str = "",
        labelPlural: str = "",
        keyPrefix: str = "",
        custom: bool = False,
        customSetting: bool = False,
        createable: bool = False,
        updateable: bool = False,
        deletable: bool = False,
        undeletable: bool = False,
        mergeable: bool = False,
        queryable: bool = False,
        feedEnabled: bool = False,
        searchable: bool = False,
        layoutable: bool = False,
        activateable: bool = False,
        fields: list[SObjectFieldDescribe] | None = None,
        childRelationships: list[dict] | None = None,
        recordTypeInfos: list[dict] | None = None,
        **additional_properties,
    ):
        self.name = name
        self.label = label
        self.labelPlural = labelPlural
        self.keyPrefix = keyPrefix
        self.custom = custom
        self.customSetting = customSetting
        self.createable = createable
        self.updateable = updateable
        self.deletable = deletable
        self.undeletable = undeletable
        self.mergeable = mergeable
        self.queryable = queryable
        self.feedEnabled = feedEnabled
        self.searchable = searchable
        self.layoutable = layoutable
        self.activateable = activateable
        self.fields = fields or []
        self.childRelationships = childRelationships or []
        self.recordTypeInfos = recordTypeInfos or []
        self._raw_data = {**additional_properties}

        # Add all explicit properties to _raw_data too
        for key, value in self.__dict__.items():
            if not key.startswith("_"):
                self._raw_data[key] = value

    @classmethod
    def from_dict(cls, data: dict) -> "SObjectDescribe":
        """Create an SObjectDescribe instance from a dictionary (typically from a Salesforce API response)"""
        # Extract fields specifically to convert them to SObjectFieldDescribe objects
        fields_data = data.pop("fields", []) if "fields" in data else []
        describe_fields = SObjectFieldDescribe._fields
        # Create SObjectFieldDescribe instances for each field
        fields = [
            SObjectFieldDescribe(
                **{k: v for k, v in field_data.items() if k in describe_fields}
            )
            for field_data in fields_data
        ]

        # Create the SObjectDescribe with all remaining properties
        return cls(fields=fields, **data)

    def get_field(self, field_name: str) -> SObjectFieldDescribe | None:
        """Get the field metadata for a specific field by name"""
        for field in self.fields:
            if field.name == field_name:
                return field
        return None

    def get_raw_data(self) -> dict:
        """Get the raw JSON data from the describe call"""
        return self._raw_data


class SObject(FieldConfigurableObject, I_SObject, ABC):
    def __init_subclass__(
        cls,
        api_name: str | None = None,
        connection: str = "",
        id_field: str = "Id",
        tooling: bool = False,
        **kwargs,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if not api_name:
            api_name = cls.__name__
        blob_field = None
        connection = connection or I_SalesforceClient.DEFAULT_CONNECTION_NAME
        for name, field in object_fields(cls).items():
            if isinstance(field, BlobField):
                assert blob_field is None, (
                    "Cannot have multiple Field/Blob fields on a single object"
                )
                blob_field = name

        if blob_field:
            del object_fields(cls)[blob_field]
        cls.attributes = SObjectAttributes(
            api_name, connection, id_field, blob_field, tooling
        )

    def __init__(self, /, **fields):
        fields.pop("attributes", None)
        blob_value = None
        if self.attributes.blob_field:
            blob_value = fields.pop(self.attributes.blob_field, None)
        super().__init__(**fields)
        if self.attributes.blob_field and blob_value is not None:
            setattr(self, self.attributes.blob_field, blob_value)

    def _has_blob_content(self) -> bool:
        """
        Check if the SObject instance has any BlobFields with content set
        """
        if not self.attributes.blob_field:
            return False
        if self.attributes.blob_field in self._values:
            return True
        return False


def _is_sobject(value):
    return isinstance(value, SObject)


def _is_sobject_subclass(cls):
    return issubclass(cls, SObject)


class SObjectList(list[_sObject]):
    """A list that contains SObject instances and provides bulk operations via Salesforce's composite API."""

    def __init__(self, iterable: Iterable[_sObject] = (), *, connection: str = ""):
        """
        Initialize an SObjectList.

        Args:
            iterable: An optional iterable of SObject instances
            connection: Optional name of the Salesforce connection to use
        """
        # items must be captured first because the iterable may be a generator,
        # and validating items before they are added to the list
        super().__init__(iterable)
        # Validate all items are SObjects
        for item in self:
            if not isinstance(item, SObject):
                raise TypeError(
                    f"All items must be SObject instances, got {type(item)}"
                )

        self.connection = connection

    @classmethod
    async def async_init(
        cls, a_iterable: AsyncIterable[_sObject], connection: str = ""
    ):
        collected_records = [record async for record in a_iterable]
        return cls(collected_records, connection=connection)

    def append(self, item: _sObject | Any):
        """Add an SObject to the list."""
        if not isinstance(item, SObject):
            raise TypeError(f"Can only append SObject instances, got {type(item)}")
        super().append(item)  # type: ignore

    def extend(self, iterable):
        """Extend the list with an iterable of SObjects."""
        if not isinstance(iterable, (tuple, list, set)):
            # ensure that we're not going to be exhausting a generator and losing items.
            iterable = tuple(iterable)
        for item in iterable:
            if not isinstance(item, SObject):
                raise TypeError(
                    f"All items must be SObject instances, got {type(item)}"
                )
        super().extend(iterable)

    def _get_client(self):
        """Get the Salesforce client to use for operations."""
        if self.connection:
            return sftk_client.SalesforceClient.get_connection(self.connection)
        elif self:
            return sftk_client.SalesforceClient.get_connection(
                self[0].attributes.connection
            )
        else:
            raise ValueError(
                "Cannot determine Salesforce connection: list is empty and no connection specified"
            )

    def _ensure_consistent_sobject_type(self) -> type[SObject] | None:
        """Validate that all SObjects in the list are of the same type."""
        if not self:
            return None

        first_type = type(self[0])
        for i, obj in enumerate(self[1:], 1):
            if type(obj) is not first_type:
                raise TypeError(
                    f"All objects must be of the same type. First item is {first_type.__name__}, "
                    f"but item at index {i} is {type(obj).__name__}"
                )
        return first_type

    def _generate_record_batches(
        self,
        max_batch_size: int = 200,
        only_changes: bool = False,
        include_fields: list[str] | None = None,
    ):
        """
        Generate batches of records for processing such that Salesforce will not
        reject any given batch due to size or type.

        Excerpt from https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_composite_sobjects_collections_create.htm

        > If the request body includes objects of more than one type, they are processed as chunks.
        > For example, if the incoming objects are {account1, account2, contact1, account3},
        > the request is processed in three chunks: {{account1, account2}, {contact1}, {account3}}.
        > A single request can process up to 10 chunks.


        """
        if max_batch_size > 200:
            warnings.warn(
                f"batch size is {max_batch_size}, but Salesforce only allows 200",
            )
            max_batch_size = 200
        emitted_records: list[_sObject] = []
        batches: list[tuple[list[dict[str, Any]], list[tuple[str, BlobData]]]] = []
        previous_record = None
        batch_records: list[dict[str, Any]] = []
        batch_binary_parts: list[tuple[str, BlobData]] = []
        batch_chunk_count = 0
        for idx, record in enumerate(self):
            if only_changes and not dirty_fields(record):
                continue
            s_record = serialize_object(record, only_changes)
            if include_fields:
                rec_fields = object_fields(type(record))
                for fieldname in include_fields:
                    s_record[fieldname] = rec_fields[fieldname].format(
                        getattr(record, fieldname)
                    )
            s_record["attributes"] = {"type": record.attributes.type}
            if record.attributes.blob_field and (
                blob_value := getattr(record, record.attributes.blob_field)
            ):
                binary_part_name = "binaryPart" + str(idx)
                s_record["attributes"].update(
                    {
                        "binaryPartName": binary_part_name,
                        "binaryPartNameAlias": record.attributes.blob_field,
                    }
                )
                batch_binary_parts.append((binary_part_name, blob_value))
            if len(batch_records) >= max_batch_size:
                batches.append((batch_records, batch_binary_parts))
                batch_records = []
                batch_chunk_count = 0
                previous_record = None
            if (
                previous_record is None
                or previous_record.attributes.type != record.attributes.type
            ):
                batch_chunk_count += 1
                if batch_chunk_count > 10:
                    batches.append((batch_records, batch_binary_parts))
                    batch_records = []
                    batch_chunk_count = 0
                    previous_record = None
            batch_records.append(s_record)
            emitted_records.append(record)
            previous_record = record
        if batch_records:
            batches.append((batch_records, batch_binary_parts))
        return batches, emitted_records

    def save(
        self,
        external_id_field: str | None = None,
        only_changes: bool = False,
        concurrency: int = 1,
        batch_size: int = 200,
        all_or_none: bool = False,
        update_only: bool = False,
        **callout_options,
    ) -> list[SObjectSaveResult]:
        """
        Save all SObjects in the list, determining whether to insert, update, or upsert based on the records and parameters.

        Args:
            external_id_field: Name of the external ID field to use for upserting (if provided)
            only_changes: If True, only send changed fields for updates
            concurrency: Number of concurrent requests to make
            batch_size: Number of records to include in each batch
            all_or_none: If True, all records must succeed or all will fail
            update_only: If True with external_id_field, only update existing records
            **callout_options: Additional options to pass to the API calls

        Returns:
            list[SObjectSaveResult]: List of save results
        """
        if not self:
            return []

        # If external_id_field is provided, use upsert
        if external_id_field:
            # Create a new list to ensure all objects have the external ID field
            upsert_objects = SObjectList(
                [obj for obj in self if hasattr(obj, external_id_field)],
                connection=self.connection,
            )

            # Check if any objects are missing the external ID field
            if len(upsert_objects) != len(self):
                missing_ext_ids = sum(
                    1 for obj in self if not hasattr(obj, external_id_field)
                )
                raise ValueError(
                    f"Cannot upsert: {missing_ext_ids} records missing external ID field '{external_id_field}'"
                )

            return upsert_objects.save_upsert(
                external_id_field=external_id_field,
                concurrency=concurrency,
                batch_size=batch_size,
                only_changes=only_changes,
                all_or_none=all_or_none,
                **callout_options,
            )

        # Check if we're dealing with mixed operations (some records have IDs, some don't)
        has_ids = [obj for obj in self if getattr(obj, obj.attributes.id_field, None)]
        missing_ids = [
            obj for obj in self if not getattr(obj, obj.attributes.id_field, None)
        ]

        # If all records have IDs, use update
        if len(has_ids) == len(self):
            return self.save_update(
                only_changes=only_changes,
                concurrency=concurrency,
                batch_size=batch_size,
                **callout_options,
            )

        # If all records are missing IDs, use insert
        elif len(missing_ids) == len(self):
            if update_only:
                raise ValueError(
                    "Cannot perform update_only operation when no records have IDs"
                )
            return self.save_insert(
                concurrency=concurrency, batch_size=batch_size, **callout_options
            )

        # Mixed case - some records have IDs, some don't
        else:
            if update_only:
                # If update_only, we should only process records with IDs
                return SObjectList(has_ids, connection=self.connection).save_update(
                    only_changes=only_changes,
                    concurrency=concurrency,
                    batch_size=batch_size,
                    **callout_options,
                )

            # Otherwise, split and process separately
            results = []

            # Process updates first
            if has_ids:
                update_results = SObjectList(
                    has_ids, connection=self.connection
                ).save_update(
                    only_changes=only_changes,
                    concurrency=concurrency,
                    batch_size=batch_size,
                    **callout_options,
                )
                results.extend(update_results)

            # Then process inserts
            if missing_ids and not update_only:
                insert_results = SObjectList(
                    missing_ids, connection=self.connection
                ).save_insert(
                    concurrency=concurrency, batch_size=batch_size, **callout_options
                )
                results.extend(insert_results)

            return results

    def save_csv(self, filepath: Path | str, encoding="utf-8") -> None:
        import csv

        if isinstance(filepath, str):
            filepath = Path(filepath).resolve()
        assert self, "Cannot save an empty list"
        fieldnames = query_fields(type(self[0]))
        with filepath.open("w+", encoding=encoding) as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flatten(serialize_object(row)) for row in self)

    def save_upsert_bulk(
        self,
        external_id_field: str,
        timeout: int = 600,
        connection: I_SalesforceClient | str | None = None,
    ) -> "BulkApiIngestJob":
        """Upsert records in bulk using Salesforce Bulk API 2.0

        This method uses the Bulk API 2.0 to upsert records based on an external ID field.
        The external ID field must exist on the object and be marked as an external ID.

        Args:
            external_id_field: The API name of the external ID field to use for the upsert
            timeout: Maximum time in seconds to wait for the job to complete

        Returns:
            Dict[str, Any]: Job result information

        Raises:
            SalesforceBulkV2LoadError: If the job fails or times out
            ValueError: If the list is empty or the external ID field doesn't exist
        """
        assert self, "Cannot upsert empty SObjectList"
        global BulkApiIngestJob
        try:
            _ = BulkApiIngestJob
        except NameError:
            from .bulk import BulkApiIngestJob

        if not connection:
            connection = self[0].attributes.connection

        job = BulkApiIngestJob.init_job(
            self[0].attributes.type,
            "upsert",
            external_id_field=external_id_field,
            connection=connection,
        )

        job.upload_batches(self)

        return job

    def save_insert_bulk(
        self, connection: I_SalesforceClient | str | None = None, **callout_options
    ) -> "BulkApiIngestJob":
        """Insert records in bulk using Salesforce Bulk API 2.0

        This method uses the Bulk API 2.0 to insert records.

        Args:
            timeout: Maximum time in seconds to wait for the job to complete

        Returns:
            Dict[str, Any]: Job result information

        Raises:
            SalesforceBulkV2LoadError: If the job fails or times out
            ValueError: If the list is empty or the external ID field doesn't exist
        """
        assert self, "Cannot upsert empty SObjectList"
        global BulkApiIngestJob
        try:
            _ = BulkApiIngestJob
        except NameError:
            from .bulk import BulkApiIngestJob

        if not connection:
            connection = self[0].attributes.connection

        job = BulkApiIngestJob.init_job(
            self[0].attributes.type, "insert", connection=connection, **callout_options
        )

        job.upload_batches(self, **callout_options)

        return job

    def save_update_bulk(
        self, connection: I_SalesforceClient | str | None = None, **callout_options
    ) -> "BulkApiIngestJob":
        """Update records in bulk using Salesforce Bulk API 2.0

        This method uses the Bulk API 2.0 to update records.

        Returns:
            Dict[str, Any]: Job result information

        Raises:
            SalesforceBulkV2LoadError: If the job fails or times out
            ValueError: If the list is empty or the external ID field doesn't exist
        """
        assert self, "Cannot upsert empty SObjectList"
        global BulkApiIngestJob
        try:
            _ = BulkApiIngestJob
        except NameError:
            from .bulk import BulkApiIngestJob

        if not connection:
            connection = self[0].attributes.connection

        job = BulkApiIngestJob.init_job(
            self[0].attributes.type, "update", connection=connection, **callout_options
        )

        job.upload_batches(self, **callout_options)

        return job

    def save_json(self, filepath: Path | str, encoding="utf-8", **json_options) -> None:
        if isinstance(filepath, str):
            filepath = Path(filepath).resolve()
        with filepath.open("w+", encoding=encoding) as outfile:
            json.dump(
                [serialize_object(record) for record in self], outfile, **json_options
            )

    def save_insert(
        self,
        concurrency: int = 1,
        batch_size: int = 200,
        all_or_none: bool = False,
        **callout_options,
    ) -> list[SObjectSaveResult]:
        """
        Insert all SObjects in the list.
        https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_composite_sobjects_collections_create.htm

        Returns:
            self: The list of SObjectSaveResults indicating success or failure of each insert operation
        """
        if not self:
            return []

        sf_client = self._get_client()

        # Ensure none of the records have IDs
        for obj in self:
            if getattr(obj, obj.attributes.id_field, None):
                raise ValueError(
                    f"Cannot insert record that already has an {obj.attributes.id_field} set"
                )

        # Prepare records for insert
        record_chunks, emitted_records = self._generate_record_batches(batch_size)

        headers = {"Content-Type": "application/json"}
        if headers_option := callout_options.pop("headers", None):
            headers.update(headers_option)

        if concurrency > 1 and len(record_chunks) > 1:
            # execute async
            return asyncio.run(
                self.save_insert_async(
                    sf_client,
                    record_chunks,
                    headers,
                    concurrency,
                    all_or_none,
                    **callout_options,
                )
            )

        # execute sync
        results = []
        for records, blobs in record_chunks:
            if blobs:
                with ExitStack() as blob_context:
                    files: list[tuple[str, tuple[str | None, Any, str | None]]] = [
                        (
                            "entity_content",
                            (None, json.dumps(records), "application/json"),
                        ),
                        # (
                        #     self.attributes.blob_field,
                        #     (blob_data.filename, blob_payload, blob_data.content_type)
                        # ),
                    ]
                    for name, blob_data in blobs:
                        blob_payload = blob_context.enter_context(blob_data)
                        files.append(
                            (
                                name,
                                (
                                    blob_data.filename,
                                    blob_payload,
                                    blob_data.content_type,
                                ),
                            )
                        )
                    response = sf_client.post(
                        sf_client.composite_sobjects_url(), files=files
                    )
            else:
                response = sf_client.post(
                    sf_client.composite_sobjects_url(),
                    json={"allOrNone": all_or_none, "records": records},
                    headers=headers,
                    **callout_options,
                )
            results.extend([SObjectSaveResult(**result) for result in response.json()])

        for record, result in zip(emitted_records, results):
            if result.success:
                setattr(record, record.attributes.id_field, result.id)

        return results

    @classmethod
    async def save_insert_async(
        cls,
        sf_client: I_SalesforceClient,
        record_chunks: list[tuple[list[dict[str, Any]], list[tuple[str, BlobData]]]],
        headers: dict[str, str],
        concurrency: int,
        all_or_none: bool,
        **callout_options,
    ):
        if header_options := callout_options.pop("headers", None):
            headers.update(header_options)
        async with sf_client.as_async as a_client:
            tasks = [
                cls._save_insert_async_batch(
                    a_client,
                    sf_client.composite_sobjects_url(),
                    records,
                    blobs,
                    all_or_none,
                    headers,
                    **callout_options,
                )
                for records, blobs in record_chunks
            ]
            responses = await run_concurrently(concurrency, tasks)
            return [
                SObjectSaveResult(**result)
                for response in responses
                for result in response.json()
            ]

    @classmethod
    async def _save_insert_async_batch(
        cls,
        sf_client: I_AsyncSalesforceClient,
        url: str,
        records: list[dict[str, Any]],
        blobs: list[tuple[str, BlobData]] | None,
        all_or_none: bool,
        headers: dict[str, str],
        **callout_options,
    ):
        if blobs:
            with ExitStack() as blob_context:
                return await sf_client.post(
                    url,
                    files=[
                        (
                            "entity_content",
                            (
                                None,
                                json.dumps(
                                    {"allOrNone": all_or_none, "records": records}
                                ),
                                "application/json",
                            ),
                        ),
                        *(
                            (
                                name,
                                (
                                    blob_data.filename,
                                    blob_context.enter_context(blob_data),
                                    blob_data.content_type,
                                ),
                            )
                            for name, blob_data in blobs
                        ),
                    ],
                )
        return await sf_client.post(
            sf_client.composite_sobjects_url(),
            json={"allOrNone": all_or_none, "records": records},
            headers=headers,
            **callout_options,
        )

    def save_update(
        self,
        only_changes: bool = False,
        all_or_none: bool = False,
        concurrency: int = 1,
        batch_size: int = 200,
        **callout_options,
    ) -> list[SObjectSaveResult]:
        """
        Update all SObjects in the list.
        https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_composite_sobjects_collections_update.htm

        Args:
            only_changes: If True, only send changed fields
            concurrency: Number of concurrent requests to make
            batch_size: Number of records to include in each batch
            **callout_options: Additional options to pass to the API call

        Returns:
            list[SObjectSaveResult]: List of save results
        """
        if not self:
            return []

        sf_client = self._get_client()

        # Ensure all records have IDs
        for i, record in enumerate(self):
            id_val = getattr(record, record.attributes.id_field, None)
            if not id_val:
                raise ValueError(
                    f"Record at index {i} has no {record.attributes.id_field} for update"
                )
            if record.attributes.blob_field and getattr(
                record, record.attributes.blob_field
            ):
                raise ValueError(
                    f"Cannot update files in composite calls. "
                    f"{type(record).__name__} Record at index {i} has Blob/File "
                    f"value for field {record.attributes.blob_field}"
                )

        # Prepare records for update
        record_chunks, emitted_records = self._generate_record_batches(
            batch_size, only_changes
        )
        headers = {"Content-Type": "application/json"}
        if headers_option := callout_options.pop("headers", None):
            headers.update(headers_option)

        if concurrency > 1:
            # execute async
            return asyncio.run(
                self.save_update_async(
                    [chunk[0] for chunk in record_chunks],
                    all_or_none,
                    headers,
                    sf_client,
                    **callout_options,
                )
            )

        # execute sync
        results: list[SObjectSaveResult] = []
        for records, blobs in record_chunks:
            assert not blobs, "Cannot update collections with files"
            response = sf_client.patch(
                sf_client.composite_sobjects_url(),
                json={"allOrNone": all_or_none, "records": records},
                headers=headers,
                **callout_options,
            )
            results.extend([SObjectSaveResult(**result) for result in response.json()])

        for record, result in zip(emitted_records, results):
            if result.success:
                dirty_fields(record).clear()

        return results

    @staticmethod
    async def save_update_async(
        record_chunks: list[list[dict[str, Any]]],
        all_or_none: bool,
        headers: dict[str, str],
        sf_client: I_SalesforceClient,
        **callout_options,
    ) -> list[SObjectSaveResult]:
        async with sf_client.as_async as a_client:
            tasks = [
                a_client.post(
                    sf_client.composite_sobjects_url(),
                    json={"allOrNone": all_or_none, "records": chunk},
                    headers=headers,
                    **callout_options,
                )
                for chunk in record_chunks
            ]
            responses = await asyncio.gather(*tasks)
            return [
                SObjectSaveResult(**result)
                for response in responses
                for result in response.json()
            ]

    def save_upsert(
        self,
        external_id_field: str,
        concurrency: int = 1,
        batch_size: int = 200,
        only_changes: bool = False,
        all_or_none: bool = False,
        **callout_options,
    ):
        """
        Upsert all SObjects in the list using an external ID field.
        https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_composite_sobjects_collections_upsert.htm

        Args:
            external_id_field: Name of the external ID field to use for upserting
            concurrency: Number of concurrent requests to make
            batch_size: Number of records to include in each batch
            only_changes: If True, only send changed fields for updates
            **callout_options: Additional options to pass to the API call

        Returns:
            list[SObjectSaveResult]: List of save results
        """

        object_type = self._ensure_consistent_sobject_type()
        if not object_type:
            # no records to upsert, early return
            return []
        sf_client = self._get_client()

        # Ensure all records have the external ID field
        for i, record in enumerate(self):
            ext_id_val = getattr(record, external_id_field, None)
            if not ext_id_val:
                raise AssertionError(
                    f"Record at index {i} has no value for external ID field '{external_id_field}'"
                )
            if record.attributes.blob_field and getattr(
                record, record.attributes.blob_field
            ):
                raise ValueError(
                    f"Cannot update files in composite calls. "
                    f"{type(record).__name__} Record at index {i} has Blob/File "
                    f"value for field {record.attributes.blob_field}"
                )

        # Chunk the requests
        record_batches, emitted_records = self._generate_record_batches(
            batch_size, only_changes, include_fields=[external_id_field]
        )

        headers = {"Content-Type": "application/json"}
        if headers_option := callout_options.pop("headers", None):
            headers.update(headers_option)

        url = (
            sf_client.composite_sobjects_url(object_type.attributes.type)
            + "/"
            + external_id_field
        )
        results: list[SObjectSaveResult]
        if concurrency > 1 and len(record_batches) > 1:
            # execute async
            results = asyncio.run(
                self.save_upsert_async(
                    sf_client,
                    url,
                    [batch[0] for batch in record_batches],
                    headers,
                    concurrency,
                    all_or_none,
                    **callout_options,
                )
            )
        else:
            # execute sync
            results = []
            for record_batch in record_batches:
                response = sf_client.patch(
                    url,
                    json={"allOrNone": all_or_none, "records": record_batch[0]},
                    headers=headers,
                )

                results.extend(
                    [SObjectSaveResult(**result) for result in response.json()]
                )

        # Clear dirty fields as operations were successful
        for record, result in zip(emitted_records, results):
            if result.success:
                dirty_fields(record).clear()

        return results

    @staticmethod
    async def save_upsert_async(
        sf_client: I_SalesforceClient,
        url: str,
        record_chunks: list[list[dict[str, Any]]],
        headers: dict[str, str],
        concurrency: int,
        all_or_none: bool,
        **callout_options,
    ):
        async with sf_client.as_async as a_client:
            tasks = [
                a_client.patch(
                    url,
                    json={"allOrNone": all_or_none, "records": chunk},
                    headers=headers,
                    **callout_options,
                )
                for chunk in record_chunks
                if chunk
            ]
            responses = await run_concurrently(concurrency, tasks)

            results = [
                SObjectSaveResult(**result)
                for response in responses
                for result in response.json()
            ]

            return results

    def delete(
        self,
        clear_id_field: bool = False,
        batch_size: int = 200,
        concurrency: int = 1,
        all_or_none: bool = False,
        **callout_options,
    ):
        """
        Delete all SObjects in the list.

        Args:
            clear_id_field: If True, clear the ID field on the objects after deletion

        Returns:
            self: The list itself for method chaining
        """
        if not self:
            return []

        record_id_batches = list(
            chunked(
                [
                    record_id
                    for obj in self
                    if (record_id := getattr(obj, obj.attributes.id_field, None))
                ],
                batch_size,
            )
        )
        sf_client = self._get_client()
        results: list[SObjectSaveResult]
        if len(record_id_batches) > 1 and concurrency > 1:
            results = asyncio.run(
                self.delete_async(
                    sf_client,
                    record_id_batches,
                    all_or_none,
                    concurrency,
                    **callout_options,
                )
            )
        else:
            headers = {"Content-Type": "application/json"}
            if headers_option := callout_options.pop("headers", None):
                headers.update(headers_option)
            url = sf_client.composite_sobjects_url()
            results = []
            for batch in record_id_batches:
                response = sf_client.delete(
                    url,
                    params={"allOrNone": all_or_none, "ids": ",".join(batch)},
                    headers=headers,
                    **callout_options,
                )
                results.extend(
                    [SObjectSaveResult(**result) for result in response.json()]
                )

        if clear_id_field:
            for record, result in zip(self, results):
                if result.success:
                    delattr(record, record.attributes.id_field)

        return results

    @staticmethod
    async def delete_async(
        sf_client: I_SalesforceClient,
        record_id_batches: list[list[str]],
        all_or_none: bool,
        concurrency: int,
        **callout_options,
    ):
        """
        Delete all SObjects in the list asynchronously.

        Args:
            sf_client: The Salesforce client
            record_id_batches: List of batches of record IDs to delete
            all_or_none: If True, delete all records or none
            callout_options: Additional options for the callout

        Returns:
            List of SObjectSaveResult objects
        """
        url = sf_client.composite_sobjects_url()
        headers = {"Content-Type": "application/json"}
        if headers_option := callout_options.pop("headers", None):
            headers.update(headers_option)
        async with sf_client.as_async as async_client:
            tasks = [
                async_client.delete(
                    url,
                    params={"allOrNone": all_or_none, "ids": ",".join(record_id)},
                    headers=headers,
                    **callout_options,
                )
                for record_id in record_id_batches
            ]
            responses = await run_concurrently(concurrency, tasks)

            results = [
                SObjectSaveResult(**result)
                for response in responses
                for result in response.json()
            ]

        return results

    def assert_single_type(self):
        """Assert there is exactly one type of record in the list"""
        assert len(self) > 0, "There must be at least one record."
        record_type = type(self[0])
        assert all(isinstance(record, record_type) for record in self), (
            "Records must be of the same type."
        )
