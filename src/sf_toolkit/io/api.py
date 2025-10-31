# pyright: reportAny=false, reportExplicitAny=false
import asyncio
from collections.abc import Callable, Container, Coroutine
from contextlib import ExitStack
import json
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote_plus
import warnings

from httpx import Response
from sf_toolkit._models import SObjectSaveResult
from sf_toolkit.async_utils import run_concurrently
from sf_toolkit.data.transformers import chunked, flatten

from ..data.fields import (
    FIELD_TYPE_LOOKUP,
    BlobData,
    Field,
    FieldConfigurableObject,
    FieldFlag,
    IdField,
    dirty_fields,
    object_fields,
    query_fields,
    serialize_object,
)
from ..data.sobject import SObject, SObjectDescribe, SObjectList
from ..data.bulk import BulkApiIngestJob

from ..logger import getLogger
from ..client import AsyncSalesforceClient, SalesforceClient


_logger = getLogger(__name__)
_sObject = TypeVar("_sObject", bound=SObject)


def resolve_client(
    cls: type[_sObject], client: SalesforceClient | None = None
) -> SalesforceClient:
    if isinstance(client, SalesforceClient):
        return client
    return SalesforceClient.get_connection(cls.attributes.connection)


def resolve_async_client(
    cls: type[_sObject], client: AsyncSalesforceClient | None = None
):
    if client:
        return client
    return AsyncSalesforceClient.get_connection(cls.attributes.connection)


def fetch(
    cls: type[_sObject],
    record_id: str,
    sf_client: SalesforceClient | None = None,
) -> _sObject:
    sf_client = resolve_client(cls, sf_client)

    if cls.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{cls.attributes.type}/{record_id}"
    else:
        url = f"{sf_client.sobjects_url}/{cls.attributes.type}/{record_id}"

    fields = list(object_fields(cls).keys())
    response_data = sf_client.get(url, params={"fields": ",".join(fields)}).json()

    return cls(**response_data)


async def fetch_async(
    cls: type[_sObject],
    record_id: str,
    sf_client: AsyncSalesforceClient | None = None,
) -> _sObject:
    sf_client = resolve_async_client(cls, sf_client)

    if cls.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{cls.attributes.type}/{record_id}"
    else:
        url = f"{sf_client.sobjects_url}/{cls.attributes.type}/{record_id}"

    fields = list(object_fields(cls).keys())
    response_data = (
        await sf_client.get(url, params={"fields": ",".join(fields)})
    ).json()

    return cls(**response_data)


def save_insert(
    record: SObject,
    sf_client: SalesforceClient | None = None,
    reload_after_success: bool = False,
):
    sf_client = resolve_client(type(record), sf_client)

    # Assert that there is no ID on the record
    if _id := getattr(record, record.attributes.id_field, None):
        raise ValueError(
            f"Cannot insert record that already has an {record.attributes.id_field} set: {_id}"
        )

    # Prepare the payload with all fields
    payload = serialize_object(record)

    if record.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{record.attributes.type}"
    else:
        url = f"{sf_client.sobjects_url}/{record.attributes.type}"

    blob_data: BlobData | None = None
    # Create a new record
    if record.attributes.blob_field and (
        blob_data := getattr(record, record.attributes.blob_field)
    ):
        with blob_data as blob_payload:
            # use BlobData context manager to safely open & close files
            response_data = sf_client.post(
                url,
                files=[
                    (
                        "entity_document",
                        (None, json.dumps(payload), "application/json"),
                    ),
                    (
                        record.attributes.blob_field,
                        (blob_data.filename, blob_payload, blob_data.content_type),
                    ),
                ],
            ).json()
    else:
        response_data = sf_client.post(
            url,
            json=payload,
        ).json()

    # Set the new ID on the object
    _id_val = response_data["id"]
    setattr(record, record.attributes.id_field, _id_val)

    # Reload the record if requested
    if reload_after_success:
        reload(record, sf_client)

    # Clear dirty fields since we've saved
    dirty_fields(record).clear()

    return


async def save_insert_async(
    record: SObject,
    sf_client: AsyncSalesforceClient | None = None,
    reload_after_success: bool = False,
):
    sf_client = resolve_async_client(type(record), sf_client)

    # Assert that there is no ID on the record
    if _id := getattr(record, record.attributes.id_field, None):
        raise ValueError(
            f"Cannot insert record that already has an {record.attributes.id_field} set: {_id}"
        )

    # Prepare the payload with all fields
    payload = serialize_object(record)

    if record.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{record.attributes.type}"
    else:
        url = f"{sf_client.sobjects_url}/{record.attributes.type}"

    blob_data: BlobData | None = None
    # Create a new record
    if record.attributes.blob_field and (
        blob_data := getattr(record, record.attributes.blob_field)
    ):
        with blob_data as blob_payload:
            # use BlobData context manager to safely open & close files
            response_data = (
                await sf_client.post(
                    url,
                    files=[
                        (
                            "entity_document",
                            (None, json.dumps(payload), "application/json"),
                        ),
                        (
                            record.attributes.blob_field,
                            (blob_data.filename, blob_payload, blob_data.content_type),
                        ),
                    ],
                )
            ).json()
    else:
        response_data = (
            await sf_client.post(
                url,
                json=payload,
            )
        ).json()

    # Set the new ID on the object
    _id_val = response_data["id"]
    setattr(record, record.attributes.id_field, _id_val)

    # Reload the record if requested
    if reload_after_success:
        await reload_async(record, sf_client)

    # Clear dirty fields since we've saved
    dirty_fields(record).clear()

    return


def save_update(
    record: SObject,
    sf_client: SalesforceClient | None = None,
    only_changes: bool = False,
    reload_after_success: bool = False,
    only_blob: bool = False,  # pyright: ignore[reportUnusedParameter]
):
    sf_client = resolve_client(type(record), sf_client)

    # Assert that there is an ID on the record
    if not (_id_val := getattr(record, record.attributes.id_field, None)):
        raise ValueError(f"Cannot update record without {record.attributes.id_field}")

    # If only tracking changes and there are no changes, do nothing
    if only_changes and not dirty_fields(record):
        return

    # Prepare the payload
    payload = serialize_object(record, only_changes)
    payload.pop(record.attributes.id_field, None)

    if record.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{record.attributes.type}/{_id_val}"
    else:
        url = f"{sf_client.sobjects_url}/{record.attributes.type}/{_id_val}"

    blob_data: BlobData | None = None
    # Create a new record
    if record.attributes.blob_field and (
        blob_data := getattr(record, record.attributes.blob_field)
    ):
        with blob_data as blob_payload:
            # use BlobData context manager to safely open & close files
            sf_client.patch(
                url,
                files=[
                    (
                        "entity_content",
                        (None, json.dumps(payload), "application/json"),
                    ),
                    (
                        record.attributes.blob_field,
                        (blob_data.filename, blob_payload, blob_data.content_type),
                    ),
                ],
            ).json()
    elif payload:
        _ = sf_client.patch(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    # Reload the record if requested
    if reload_after_success:
        reload(record, sf_client)

    # Clear dirty fields since we've saved
    dirty_fields(record).clear()

    return


async def save_update_async(
    record: SObject,
    sf_client: AsyncSalesforceClient | None = None,
    only_changes: bool = False,
    reload_after_success: bool = False,
    only_blob: bool = False,  # pyright: ignore[reportUnusedParameter]
):
    sf_client = resolve_async_client(type(record), sf_client)

    # Assert that there is an ID on the record
    if not (_id_val := getattr(record, record.attributes.id_field, None)):
        raise ValueError(f"Cannot update record without {record.attributes.id_field}")

    # If only tracking changes and there are no changes, do nothing
    if only_changes and not dirty_fields(record):
        return

    # Prepare the payload
    payload = serialize_object(record, only_changes)
    payload.pop(record.attributes.id_field, None)

    if record.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{record.attributes.type}/{_id_val}"
    else:
        url = f"{sf_client.sobjects_url}/{record.attributes.type}/{_id_val}"

    blob_data: BlobData | None = None
    # Create a new record
    if record.attributes.blob_field and (
        blob_data := getattr(record, record.attributes.blob_field)
    ):
        with blob_data as blob_payload:
            # use BlobData context manager to safely open & close files
            (
                await sf_client.patch(
                    url,
                    files=[
                        (
                            "entity_content",
                            (None, json.dumps(payload), "application/json"),
                        ),
                        (
                            record.attributes.blob_field,
                            (blob_data.filename, blob_payload, blob_data.content_type),
                        ),
                    ],
                )
            ).json()
    elif payload:
        _ = await sf_client.patch(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    # Reload the record if requested
    if reload_after_success:
        await reload_async(record, sf_client)

    # Clear dirty fields since we've saved
    dirty_fields(record).clear()

    return


def save_upsert(
    record: SObject,
    external_id_field: str,
    sf_client: SalesforceClient | None = None,
    reload_after_success: bool = False,
    update_only: bool = False,
    only_changes: bool = False,
):
    if record.attributes.tooling:
        raise TypeError("Upsert is not available for Tooling SObjects.")

    sf_client = resolve_client(type(record), sf_client)

    # Get the external ID value
    if not (ext_id_val := getattr(record, external_id_field, None)):
        raise ValueError(
            f"Cannot upsert record without a value for external ID field: {external_id_field}"
        )

    # Encode the external ID value in the URL to handle special characters
    ext_id_val = quote_plus(str(ext_id_val))

    # Prepare the payload
    payload = serialize_object(record, only_changes)
    payload.pop(external_id_field, None)

    # If there's nothing to update when only_changes=True, just return
    if only_changes and not payload:
        return

    # Execute the upsert
    response = sf_client.patch(
        f"{sf_client.sobjects_url}/{record.attributes.type}/{external_id_field}/{ext_id_val}",
        json=payload,
        params={"updateOnly": update_only} if update_only else None,
        headers={"Content-Type": "application/json"},
    )

    # For an insert via upsert, the response contains the new ID
    if response.is_success:
        response_data = response.json()
        _id_val = response_data.get("id")
        if _id_val:
            setattr(record, record.attributes.id_field, _id_val)
    elif update_only and response.status_code == 404:
        raise ValueError(
            f"Record not found for external ID field {external_id_field} with value {ext_id_val}"
        )

    # Reload the record if requested
    if reload_after_success and (
        _id_val := getattr(record, record.attributes.id_field, None)
    ):
        reload(record, sf_client)

    # Clear dirty fields since we've saved
    dirty_fields(record).clear()

    return record


async def save_upsert_async(
    record: SObject,
    external_id_field: str,
    sf_client: AsyncSalesforceClient | None = None,
    reload_after_success: bool = False,
    update_only: bool = False,
    only_changes: bool = False,
):
    if record.attributes.tooling:
        raise TypeError("Upsert is not available for Tooling SObjects.")

    sf_client = resolve_async_client(type(record), sf_client)

    # Get the external ID value
    if not (ext_id_val := getattr(record, external_id_field, None)):
        raise ValueError(
            f"Cannot upsert record without a value for external ID field: {external_id_field}"
        )

    # Encode the external ID value in the URL to handle special characters
    ext_id_val = quote_plus(str(ext_id_val))

    # Prepare the payload
    payload = serialize_object(record, only_changes)
    payload.pop(external_id_field, None)

    # If there's nothing to update when only_changes=True, just return
    if only_changes and not payload:
        return

    # Execute the upsert
    response = await sf_client.patch(
        f"{sf_client.sobjects_url}/{record.attributes.type}/{external_id_field}/{ext_id_val}",
        json=payload,
        params={"updateOnly": update_only} if update_only else None,
        headers={"Content-Type": "application/json"},
    )

    # For an insert via upsert, the response contains the new ID
    if response.is_success:
        response_data = response.json()
        _id_val = response_data.get("id")
        if _id_val:
            setattr(record, record.attributes.id_field, _id_val)
    elif update_only and response.status_code == 404:
        raise ValueError(
            f"Record not found for external ID field {external_id_field} with value {ext_id_val}"
        )

    # Reload the record if requested
    if reload_after_success and (
        _id_val := getattr(record, record.attributes.id_field, None)
    ):
        await reload_async(record, sf_client)

    # Clear dirty fields since we've saved
    dirty_fields(record).clear()

    return record


def sobject_save_csv(
    record: SObject, filepath: Path | str, encoding: str = "utf-8"
) -> None:
    import csv

    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open("w+", encoding=encoding) as outfile:
        writer = csv.DictWriter(outfile, fieldnames=query_fields(type(record)))
        writer.writeheader()
        writer.writerow(flatten(serialize_object(record)))


def sobject_save_json(
    record: SObject, filepath: Path | str, encoding: str = "utf-8", **json_options: Any
) -> None:
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open("w+", encoding=encoding) as outfile:
        json.dump(serialize_object(record), outfile, **json_options)


def save(
    self: SObject,
    sf_client: SalesforceClient | None = None,
    only_changes: bool = False,
    reload_after_success: bool = False,
    external_id_field: str | None = None,
    update_only: bool = False,
):
    """
    Generic save function that decides whether to insert, update, or upsert
    the record based on its state and provided parameters.
    """

    # If we have an ID value, use save_update
    if getattr(self, self.attributes.id_field, None) is not None:
        return save_update(
            self,
            sf_client=sf_client,
            only_changes=only_changes,
            reload_after_success=reload_after_success,
        )
    # If we have an external ID field, use save_upsert
    elif external_id_field:
        return save_upsert(
            self,
            external_id_field=external_id_field,
            sf_client=sf_client,
            reload_after_success=reload_after_success,
            update_only=update_only,
            only_changes=only_changes,
        )
    # Otherwise, if not update_only, use save_insert
    elif not update_only:
        return save_insert(
            self, sf_client=sf_client, reload_after_success=reload_after_success
        )
    else:
        # If update_only is True and there's no ID or external ID, raise an error
        raise ValueError("Cannot update record without an ID or external ID")


async def save_async(
    self: SObject,
    sf_client: AsyncSalesforceClient | None = None,
    only_changes: bool = False,
    only_blob: bool = False,
    reload_after_success: bool = False,
    external_id_field: str | None = None,
    update_only: bool = False,
):
    # If we have an ID value, use save_update
    if getattr(self, self.attributes.id_field, None) is not None:
        return await save_update_async(
            self,
            sf_client=sf_client,
            only_changes=only_changes,
            reload_after_success=reload_after_success,
            only_blob=only_blob,
        )
    # If we have an external ID field, use save_upsert
    elif external_id_field:
        return await save_upsert_async(
            self,
            external_id_field=external_id_field,
            sf_client=sf_client,
            reload_after_success=reload_after_success,
            update_only=update_only,
            only_changes=only_changes,
        )
    # Otherwise, if not update_only, use save_insert
    elif not update_only:
        return await save_insert_async(
            self, sf_client=sf_client, reload_after_success=reload_after_success
        )
    else:
        # If update_only is True and there's no ID or external ID, raise an error
        raise ValueError("Cannot update record without an ID or external ID")


def delete(
    record: SObject,
    sf_client: SalesforceClient | None = None,
    clear_id_field: bool = True,
):
    sf_client = resolve_client(type(record), sf_client)
    _id_val = getattr(record, record.attributes.id_field, None)

    if not _id_val:
        raise ValueError("Cannot delete unsaved record (missing ID to delete)")

    if record.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{record.attributes.type}/{_id_val}"
    else:
        url = f"{sf_client.sobjects_url}/{record.attributes.type}/{_id_val}"
    _ = sf_client.delete(url).raise_for_status()
    if clear_id_field:
        delattr(record, record.attributes.id_field)


async def delete_async(
    record: SObject,
    sf_client: AsyncSalesforceClient | None = None,
    clear_id_field: bool = True,
):
    sf_client = resolve_async_client(type(record), sf_client)
    _id_val = getattr(record, record.attributes.id_field, None)

    if not _id_val:
        raise ValueError("Cannot delete unsaved record (missing ID to delete)")

    if record.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{record.attributes.type}/{_id_val}"
    else:
        url = f"{sf_client.sobjects_url}/{record.attributes.type}/{_id_val}"
    _ = (await sf_client.delete(url)).raise_for_status()
    if clear_id_field:
        delattr(record, record.attributes.id_field)


def download_file(
    record: SObject, dest: Path | None, sf_client: SalesforceClient | None = None
) -> None | bytes:
    """
    Download the file associated with the blob field to the specified destination.
    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/dome_sobject_blob_retrieve.htm

    Args:
        dest (Path | None): The destination path to save the file.
        If None, file content will be returned as bytes instead.
    """
    assert record.attributes.blob_field, "Object type must specify a blob field"
    assert not record.attributes.tooling, (
        "Cannot download file/BLOB from tooling object"
    )
    record_id = getattr(record, record.attributes.id_field, None)
    assert record_id, "Record ID cannot be None or Empty for file download"

    sf_client = resolve_client(type(record), sf_client)
    url = (
        f"{sf_client.sobjects_url}/{record.attributes.type}"
        f"/{record_id}/{record.attributes.blob_field}"
    )
    with sf_client.stream("GET", url) as response:
        if dest:
            with dest.open("wb") as file:
                for block in response.iter_bytes():
                    _ = file.write(block)
            return None

        else:
            return response.read()


async def download_file_async(
    record: SObject, dest: Path | None, sf_client: AsyncSalesforceClient | None = None
) -> None | bytes:
    """
    Download the file associated with the blob field to the specified destination.
    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/dome_sobject_blob_retrieve.htm

    Args:
        dest (Path | None): The destination path to save the file.
        If None, file content will be returned as bytes instead.
    """
    assert record.attributes.blob_field, "Object type must specify a blob field"
    assert not record.attributes.tooling, (
        "Cannot download file/BLOB from tooling object"
    )
    record_id = getattr(record, record.attributes.id_field, None)
    assert record_id, "Record ID cannot be None or Empty for file download"

    sf_client = resolve_async_client(type(record), sf_client)
    url = (
        f"{sf_client.sobjects_url}/{record.attributes.type}"
        f"/{record_id}/{record.attributes.blob_field}"
    )
    async with sf_client.stream("GET", url) as response:
        if dest:
            with dest.open("wb") as file:
                for block in response.iter_bytes():
                    _ = file.write(block)
            return None

        else:
            return response.read()


def reload(record: SObject, sf_client: SalesforceClient | None = None):
    record_id: str = getattr(record, record.attributes.id_field)
    sf_client = resolve_client(type(record), sf_client)
    reloaded = fetch(type(record), record_id, sf_client)
    record._values.update(reloaded._values)  # pyright: ignore[reportPrivateUsage]


async def reload_async(record: SObject, sf_client: AsyncSalesforceClient | None = None):
    record_id: str = getattr(record, record.attributes.id_field)
    sf_client = resolve_async_client(type(record), sf_client)
    reloaded = await fetch_async(type(record), record_id, sf_client)
    record._values.update(reloaded._values)  # pyright: ignore[reportPrivateUsage]


def update_record(record: FieldConfigurableObject, /, **props: Any):
    _fields = object_fields(type(record))
    for key, value in props.items():
        if key in _fields:
            setattr(record, key, value)


def fetch_list(
    cls: type[_sObject],
    *ids: str,
    sf_client: SalesforceClient | None = None,
    on_chunk_received: Callable[[Response], None] | None = None,
) -> "SObjectList[_sObject]":
    sf_client = resolve_client(cls, sf_client)

    if len(ids) == 1:
        return SObjectList(
            [fetch(cls, ids[0], sf_client)], connection=cls.attributes.connection
        )

    # pull in batches with composite API
    result: SObjectList[_sObject] = SObjectList(connection=cls.attributes.connection)
    for chunk in chunked(ids, 2000):
        response = sf_client.post(
            sf_client.composite_sobjects_url(cls.attributes.type),
            json={"ids": chunk, "fields": query_fields(cls)},
        )
        result.extend([cls(**record) for record in response.json()])  # pyright: ignore[reportUnknownMemberType]
        if on_chunk_received:
            on_chunk_received(response)
    return result


async def fetch_list_async(
    cls: type[_sObject],
    *ids: str,
    sf_client: AsyncSalesforceClient | None = None,
    concurrency: int = 1,
    on_chunk_received: Callable[[Response], Coroutine[None, None, None] | None]
    | None = None,
) -> "SObjectList[_sObject]":
    sf_client = resolve_async_client(cls, sf_client)
    async with sf_client:
        tasks = [
            sf_client.post(
                sf_client.composite_sobjects_url(cls.attributes.type),
                json={"ids": chunk, "fields": query_fields(cls)},
            )
            for chunk in chunked(ids, 2000)
        ]
        records: SObjectList[_sObject] = SObjectList(
            (  # type: ignore
                cls(**record)
                for response in (
                    await run_concurrently(concurrency, tasks, on_chunk_received)
                )
                for record in response.json()
            ),
            connection=cls.attributes.connection,
        )
        return records


def sobject_describe(cls: type[_sObject]):
    """
    Retrieves detailed metadata information about the SObject from Salesforce.

    Returns:
        dict: The full describe result containing metadata about the SObject's
              fields, relationships, and other properties.
    """
    sf_client = resolve_client(cls, None)

    # Use the describe endpoint for this SObject type
    describe_url = f"{sf_client.sobjects_url}/{cls.attributes.type}/describe"

    # Make the request to get the describe metadata
    response = sf_client.get(describe_url)

    # Return the describe metadata as a dictionary
    return response.json()


def sobject_from_description(
    sobject: str,
    connection: str = "",
    ignore_fields: Container[str] | None = None,
    base_class: type[_sObject] = SObject,
) -> type[_sObject]:
    """
    Build an SObject type definition for the named SObject based on the object 'describe' from Salesforce

    Args:
        sobject (str): The API name of the SObject in Salesforce
        connection (str): The name of the Salesforce connection to use

    Returns:
        type[SObject]: A dynamically created SObject subclass with fields matching the describe result
    """
    sf_client = SalesforceClient.get_connection(connection)

    # Get the describe metadata for this SObject
    describe_url = f"{sf_client.sobjects_url}/{sobject}/describe"
    describe_data = SObjectDescribe.from_dict(sf_client.get(describe_url).json())

    # Extract field information
    fields = {}
    for field in describe_data.fields:
        if ignore_fields and field.name in ignore_fields:
            continue
        if field.type == "reference":
            field_cls = IdField
        elif field.type in FIELD_TYPE_LOOKUP:
            field_cls: type[Field[Any]] = FIELD_TYPE_LOOKUP[field.type]
        else:
            _logger.error(
                "Unsupported field type '%s' for field '%s.%s'",
                field.type,
                sobject,
                field.name,
            )
            continue
        kwargs: dict[str, Any] = {}
        flags: list[FieldFlag] = []

        if not field.updateable:
            flags.append(FieldFlag.readonly)

        fields[field.name] = field_cls(*flags, **kwargs)  # type: ignore

    # Create a new SObject subclass
    sobject_class = type(
        f"SObject__{sobject}",
        (base_class,),
        {
            "__doc__": f"Auto-generated SObject class for {sobject} ({describe_data.label})",
            **fields,
        },
        api_name=sobject,
        connection=connection,
    )

    return sobject_class  # pyright: ignore[reportReturnType]


### SOBJECT LIST OPERATORS ###


def _ensure_consistent_sobject_type(
    self: SObjectList[_sObject],
) -> type[_sObject] | None:
    """Validate that all SObjects in the list are of the same type."""
    if not self:
        return None

    first_type = type(self[0])
    for i, obj in enumerate(self[1:], 1):
        if type(obj) is not first_type:
            raise TypeError(
                (
                    f"All objects must be of the same type. First item is {first_type.__name__}, "
                    f"but item at index {i} is {type(obj).__name__}"
                )
            )
    return first_type


def _generate_record_batches(
    self: SObjectList[_sObject],
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


def save_list(
    self: SObjectList[_sObject],
    external_id_field: str | None = None,
    only_changes: bool = False,
    batch_size: int = 200,
    all_or_none: bool = False,
    update_only: bool = False,
    **callout_options: Any,
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

        return save_upsert_list(
            upsert_objects,
            external_id_field=external_id_field,
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
        return save_update_list(
            self,
            only_changes=only_changes,
            batch_size=batch_size,
            **callout_options,
        )

    # If all records are missing IDs, use insert
    elif len(missing_ids) == len(self):
        if update_only:
            raise ValueError(
                "Cannot perform update_only operation when no records have IDs"
            )
        return save_insert_list(self, batch_size=batch_size, **callout_options)

    # Mixed case - some records have IDs, some don't
    else:
        if update_only:
            # If update_only, we should only process records with IDs
            return save_update_list(
                SObjectList(has_ids, connection=self.connection),
                only_changes=only_changes,
                batch_size=batch_size,
                **callout_options,
            )

        # Otherwise, split and process separately
        results: list[SObjectSaveResult] = []

        # Process updates first
        if has_ids:
            update_results = save_update_list(
                SObjectList(has_ids, connection=self.connection),
                only_changes=only_changes,
                batch_size=batch_size,
                **callout_options,
            )
            results.extend(update_results)

        # Then process inserts
        if missing_ids and not update_only:
            insert_results = save_insert_list(
                SObjectList(missing_ids, connection=self.connection),
                batch_size=batch_size,
                **callout_options,
            )
            results.extend(insert_results)

        return results


def save_upsert_bulk(
    self: SObjectList[_sObject],
    external_id_field: str,
    connection: SalesforceClient | str | None = None,
    **callout_options: Any,
) -> BulkApiIngestJob:
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

    if not connection:
        connection = self[0].attributes.connection

    job = BulkApiIngestJob.init_job(
        self[0].attributes.type,
        "upsert",
        external_id_field=external_id_field,
        connection=connection,
        **callout_options,
    )

    _ = job.upload_batches(self, **callout_options)

    return job


async def save_upsert_bulk_async(
    self: SObjectList[_sObject],
    external_id_field: str,
    connection: AsyncSalesforceClient | str | None = None,
) -> BulkApiIngestJob:
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

    if not connection:
        connection = self[0].attributes.connection

    job = await BulkApiIngestJob.init_job_async(
        self[0].attributes.type,
        "upsert",
        external_id_field=external_id_field,
        connection=connection,
    )

    _ = await job.upload_batches_async(self)

    return job


def save_insert_bulk(
    self: SObjectList[_sObject],
    connection: SalesforceClient | str | None = None,
    **callout_options: Any,
) -> BulkApiIngestJob:
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

    if not connection:
        connection = self[0].attributes.connection

    job = BulkApiIngestJob.init_job(
        self[0].attributes.type, "insert", connection=connection, **callout_options
    )

    _ = job.upload_batches(self, **callout_options)

    return job


async def save_insert_bulk_async(
    records: SObjectList[_sObject],
    connection: AsyncSalesforceClient | str | None = None,
    **callout_options: Any,
) -> BulkApiIngestJob | None:
    """Insert records in bulk using Salesforce Bulk API 2.0

    This method uses the Bulk API 2.0 to insert records.

    Returns:
        Dict[str, Any]: Job result information

    Raises:
        SalesforceBulkV2LoadError: If the job fails or times out
        ValueError: If the list is empty or the external ID field doesn't exist
    """
    if not records:
        warnings.warn("Cannot update empty SObjectList")
        return None

    if not connection:
        connection = records[0].attributes.connection

    job: BulkApiIngestJob = await BulkApiIngestJob.init_job_async(
        records[0].attributes.type, "insert", connection=connection, **callout_options
    )

    _ = await job.upload_batches_async(records, **callout_options)

    return job


def save_update_bulk(
    records: SObjectList[_sObject],
    connection: SalesforceClient | str | None = None,
    **callout_options: Any,
) -> BulkApiIngestJob | None:
    """Update records in bulk using Salesforce Bulk API 2.0

    This method uses the Bulk API 2.0 to update records.

    Returns:
        Dict[str, Any]: Job result information

    Raises:
        SalesforceBulkV2LoadError: If the job fails or times out
        ValueError: If the list is empty or the external ID field doesn't exist
    """
    if not records:
        warnings.warn("Cannot update empty SObjectList")
        return None

    if not connection:
        connection = records[0].attributes.connection

    job = BulkApiIngestJob.init_job(
        records[0].attributes.type, "update", connection=connection, **callout_options
    )

    _ = job.upload_batches(records, **callout_options)

    return job


async def save_update_bulk_async(
    records: SObjectList[_sObject],
    connection: AsyncSalesforceClient | str | None = None,
    **callout_options: Any,
) -> BulkApiIngestJob | None:
    """Update records in bulk using Salesforce Bulk API 2.0

    This method uses the Bulk API 2.0 to update records.

    Returns:
        Dict[str, Any]: Job result information

    Raises:
        SalesforceBulkV2LoadError: If the job fails or times out
        ValueError: If the list is empty or the external ID field doesn't exist
    """
    if not records:
        warnings.warn("Cannot update empty SObjectList")
        return None

    if not connection:
        connection = records[0].attributes.connection

    job: BulkApiIngestJob = await BulkApiIngestJob.init_job_async(
        records[0].attributes.type, "update", connection=connection, **callout_options
    )

    _ = await job.upload_batches_async(records, **callout_options)

    return job


def save_insert_list(
    self: SObjectList[_sObject],
    batch_size: int = 200,
    all_or_none: bool = False,
    sf_client: SalesforceClient | None = None,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    """
    Insert all SObjects in the list.
    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_composite_sobjects_collections_create.htm

    Returns:
        self: The list of SObjectSaveResults indicating success or failure of each insert operation
    """
    if not self:
        return []

    sf_client = resolve_client(type(self[0]), sf_client)

    # Ensure none of the records have IDs
    for obj in self:
        if getattr(obj, obj.attributes.id_field, None):
            raise ValueError(
                f"Cannot insert record that already has an {obj.attributes.id_field} set"
            )

    # Prepare records for insert
    record_chunks, emitted_records = _generate_record_batches(self, batch_size)

    headers = {"Content-Type": "application/json"}
    if headers_option := callout_options.pop("headers", None):
        headers.update(headers_option)

    # execute sync
    results: list[SObjectSaveResult] = []
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


async def save_insert_list_async(
    records: SObjectList[_sObject],
    concurrency: int = 5,
    batch_size: int = 200,
    all_or_none: bool = False,
    sf_client: AsyncSalesforceClient | None = None,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    """
    Insert all SObjects in the list.
    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_composite_sobjects_collections_create.htm

    Returns:
        self: The list of SObjectSaveResults indicating success or failure of each insert operation
    """
    if not records:
        return []

    sf_client = resolve_async_client(type(records[0]), sf_client)

    # Ensure none of the records have IDs
    for obj in records:
        if getattr(obj, obj.attributes.id_field, None):
            raise ValueError(
                f"Cannot insert record that already has an {obj.attributes.id_field} set"
            )

    # Prepare records for insert
    record_chunks, _ = _generate_record_batches(records, batch_size)

    headers = {"Content-Type": "application/json"}
    if headers_option := callout_options.pop("headers", None):
        headers.update(headers_option)

    return await _insert_list_chunks_async(
        sf_client,
        record_chunks,
        headers,
        concurrency,
        all_or_none,
        **callout_options,
    )


async def _insert_list_chunks_async(
    sf_client: AsyncSalesforceClient | None,
    record_chunks: list[tuple[list[dict[str, Any]], list[tuple[str, BlobData]]]],
    headers: dict[str, str],
    concurrency: int,
    all_or_none: bool,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    sf_client = sf_client or AsyncSalesforceClient.get_connection()
    if header_options := callout_options.pop("headers", None):
        headers.update(header_options)
    tasks = [
        _save_insert_async_batch(
            sf_client,
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


async def _save_insert_async_batch(
    # cls: type[SObjectList[_sObject]],
    sf_client: AsyncSalesforceClient,
    url: str,
    records: list[dict[str, Any]],
    blobs: list[tuple[str, BlobData]] | None,
    all_or_none: bool,
    headers: dict[str, str],
    **callout_options: Any,
) -> Response:
    if blobs:
        with ExitStack() as blob_context:
            return await sf_client.post(
                url,
                files=[
                    (
                        "entity_content",
                        (
                            None,
                            json.dumps({"allOrNone": all_or_none, "records": records}),
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


def save_update_list(
    self: SObjectList[_sObject],
    only_changes: bool = False,
    all_or_none: bool = False,
    batch_size: int = 200,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    """
    Update all SObjects in the list.
    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_composite_sobjects_collections_update.htm

    Args:
        only_changes: If True, only send changed fields
        batch_size: Number of records to include in each batch
        **callout_options: Additional options to pass to the API call

    Returns:
        list[SObjectSaveResult]: List of save results
    """
    if not self:
        return []

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
                (
                    f"Cannot update files in composite calls. "
                    f"{type(record).__name__} Record at index {i} has Blob/File "
                    f"value for field {record.attributes.blob_field}"
                )
            )

    # Prepare records for update
    record_chunks, emitted_records = _generate_record_batches(
        self, batch_size, only_changes
    )
    headers = {"Content-Type": "application/json"}
    if headers_option := callout_options.pop("headers", None):
        headers.update(headers_option)

    sf_client = resolve_client(type(self[0]), None)
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


async def save_update_list_async(
    self: SObjectList[_sObject],
    only_changes: bool = False,
    all_or_none: bool = False,
    batch_size: int = 200,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    """
    Update all SObjects in the list.
    https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_composite_sobjects_collections_update.htm

    Args:
        only_changes: If True, only send changed fields
        batch_size: Number of records to include in each batch
        **callout_options: Additional options to pass to the API call

    Returns:
        list[SObjectSaveResult]: List of save results
    """
    if not self:
        return []

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
                (
                    f"Cannot update files in composite calls. "
                    f"{type(record).__name__} Record at index {i} has Blob/File "
                    f"value for field {record.attributes.blob_field}"
                )
            )

    # Prepare records for update
    record_chunks, emitted_records = _generate_record_batches(
        self, batch_size, only_changes
    )
    headers = {"Content-Type": "application/json"}
    if headers_option := callout_options.pop("headers", None):
        headers.update(headers_option)

    sf_client = resolve_async_client(type(self[0]), None)
    # execute sync
    results: list[SObjectSaveResult] = await _list_save_update_async(
        [chunk[0] for chunk in record_chunks],
        all_or_none,
        headers,
        sf_client,
        **callout_options,
    )

    for record, result in zip(emitted_records, results):
        if result.success:
            dirty_fields(record).clear()

    return results


async def _list_save_update_async(
    record_chunks: list[list[dict[str, Any]]],
    all_or_none: bool,
    headers: dict[str, str],
    sf_client: AsyncSalesforceClient,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    tasks = [
        sf_client.post(
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


def save_upsert_list(
    records: SObjectList[_sObject],
    external_id_field: str,
    concurrency: int = 1,
    batch_size: int = 200,
    only_changes: bool = False,
    all_or_none: bool = False,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
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

    object_type = _ensure_consistent_sobject_type(records)
    if not object_type:
        # no records to upsert, early return
        return []
    sf_client = resolve_client(object_type, None)

    # Ensure all records have the external ID field
    for i, record in enumerate(records):
        ext_id_val = getattr(record, external_id_field, None)
        if not ext_id_val:
            raise AssertionError(
                f"Record at index {i} has no value for external ID field '{external_id_field}'"
            )
        if record.attributes.blob_field and getattr(
            record, record.attributes.blob_field
        ):
            raise ValueError(
                (
                    f"Cannot update files in composite calls. "
                    f"{type(record).__name__} Record at index {i} has Blob/File "
                    f"value for field {record.attributes.blob_field}"
                )
            )

    # Chunk the requests
    record_batches, emitted_records = _generate_record_batches(
        records, batch_size, only_changes, include_fields=[external_id_field]
    )

    headers = {"Content-Type": "application/json"}
    headers_option: dict[str, str] | None
    if headers_option := callout_options.pop("headers", None):
        headers.update(headers_option)

    url = (
        sf_client.composite_sobjects_url(object_type.attributes.type)
        + "/"
        + external_id_field
    )
    results: list[SObjectSaveResult]
    if concurrency > 1 and len(record_batches) > 1:
        sf_client = resolve_async_client(object_type, None)
        # execute async
        results = asyncio.run(
            _save_upsert_list_chunks_async(
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

            results.extend([SObjectSaveResult(**result) for result in response.json()])

    # Clear dirty fields as operations were successful
    for record, result in zip(emitted_records, results):
        if result.success:
            dirty_fields(record).clear()

    return results


async def save_upsert_list_async(
    records: SObjectList[_sObject],
    external_id_field: str,
    concurrency: int = 1,
    batch_size: int = 200,
    only_changes: bool = False,
    all_or_none: bool = False,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
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

    object_type = _ensure_consistent_sobject_type(records)
    if not object_type:
        # no records to upsert, early return
        return []
    sf_client = resolve_async_client(object_type, None)

    # Ensure all records have the external ID field
    for i, record in enumerate(records):
        ext_id_val = getattr(record, external_id_field, None)
        if not ext_id_val:
            raise AssertionError(
                f"Record at index {i} has no value for external ID field '{external_id_field}'"
            )
        if record.attributes.blob_field and getattr(
            record, record.attributes.blob_field
        ):
            raise ValueError(
                (
                    f"Cannot update files in composite calls. "
                    f"{type(record).__name__} Record at index {i} has Blob/File "
                    f"value for field {record.attributes.blob_field}"
                )
            )

    # Chunk the requests
    record_batches, emitted_records = _generate_record_batches(
        records, batch_size, only_changes, include_fields=[external_id_field]
    )

    headers = {"Content-Type": "application/json"}
    if headers_option := callout_options.pop("headers", None):
        headers.update(headers_option)

    url = (
        sf_client.composite_sobjects_url(object_type.attributes.type)
        + "/"
        + external_id_field
    )
    results: list[SObjectSaveResult] = await _save_upsert_list_chunks_async(
        sf_client,
        url,
        [batch[0] for batch in record_batches],
        headers,
        concurrency,
        all_or_none,
        **callout_options,
    )

    # Clear dirty fields as operations were successful
    for record, result in zip(emitted_records, results):
        if result.success:
            dirty_fields(record).clear()

    return results


async def _save_upsert_list_chunks_async(
    sf_client: AsyncSalesforceClient,
    url: str,
    record_chunks: list[list[dict[str, Any]]],
    headers: dict[str, str],
    concurrency: int,
    all_or_none: bool,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    tasks = [
        sf_client.patch(
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


def delete_list(
    records: SObjectList[_sObject],
    clear_id_field: bool = False,
    batch_size: int = 200,
    all_or_none: bool = False,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    """
    Delete all SObjects in the list.

    Args:
        clear_id_field: If True, clear the ID field on the objects after deletion

    Returns:
        self: The list itself for method chaining
    """
    if not records:
        return []

    record_id_batches = list(
        chunked(
            [
                record_id
                for obj in records
                if (record_id := getattr(obj, obj.attributes.id_field, None))
            ],
            batch_size,
        )
    )
    results: list[SObjectSaveResult]
    sf_client = resolve_client(type(records[0]), None)
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
        results.extend([SObjectSaveResult(**result) for result in response.json()])

    if clear_id_field:
        for record, result in zip(records, results):
            if result.success:
                delattr(record, record.attributes.id_field)

    return results


async def delete_list_async(
    records: SObjectList[_sObject],
    clear_id_field: bool = False,
    batch_size: int = 200,
    concurrency: int = 1,
    all_or_none: bool = False,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
    """
    Delete all SObjects in the list.

    Args:
        clear_id_field: If True, clear the ID field on the objects after deletion

    Returns:
        self: The list itself for method chaining
    """
    if not records:
        return []

    record_id_batches = list(
        chunked(
            [
                record_id
                for obj in records
                if (record_id := getattr(obj, obj.attributes.id_field, None))
            ],
            batch_size,
        )
    )
    results: list[SObjectSaveResult] = []
    sf_client = resolve_async_client(type(records[0]), None)
    results = await _delete_list_chunks_async(
        sf_client,
        record_id_batches,
        all_or_none,
        concurrency,
        **callout_options,
    )
    if clear_id_field:
        for record, result in zip(records, results):
            if result.success:
                delattr(record, record.attributes.id_field)

    return results


async def _delete_list_chunks_async(
    sf_client: AsyncSalesforceClient,
    record_id_batches: list[list[str]],
    all_or_none: bool,
    concurrency: int,
    **callout_options: Any,
) -> list[SObjectSaveResult]:
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
    tasks = [
        sf_client.delete(
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
