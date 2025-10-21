import asyncio
from collections.abc import Callable, Container, Coroutine
import json
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote_plus

from httpx import Response
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

from ..logger import getLogger
from ..data.sobject import SObject, SObjectDescribe, SObjectList
from ..interfaces import I_AsyncSalesforceClient, I_SalesforceClient
from ..client import SalesforceClient as sftk_client

_logger = getLogger(__name__)
_sObject = TypeVar("_sObject", bound=SObject)


def resolve_client(
    cls: type[_sObject], client: I_SalesforceClient | None = None
) -> I_SalesforceClient:
    if client:
        return client
    return sftk_client.get_connection(cls.attributes.connection)


def resolve_async_client(
    cls: type[_sObject], client: I_AsyncSalesforceClient | None = None
):
    if client:
        return client
    return sftk_client.get_connection(cls.attributes.connection).as_async


def fetch(
    cls: type[_sObject],
    record_id: str,
    sf_client: I_SalesforceClient | None = None,
) -> _sObject:
    sf_client = resolve_client(cls, sf_client)

    if cls.attributes.tooling:
        url = f"{sf_client.tooling_sobjects_url}/{cls.attributes.type}/{record_id}"
    else:
        url = f"{sf_client.sobjects_url}/{cls.attributes.type}/{record_id}"

    fields = list(object_fields(cls).keys())
    response_data = sf_client.get(url, params={"fields": ",".join(fields)}).json()

    return cls(**response_data)


def save_insert(
    record: SObject,
    sf_client: I_SalesforceClient | None = None,
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


def save_update(
    record: SObject,
    sf_client: I_SalesforceClient | None = None,
    only_changes: bool = False,
    reload_after_success: bool = False,
    only_blob: bool = False,
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


def save_upsert(
    record: SObject,
    external_id_field: str,
    sf_client: I_SalesforceClient | None = None,
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
    record: SObject, filepath: Path | str, encoding: str = "utf-8", **json_options
) -> None:
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open("w+", encoding=encoding) as outfile:
        json.dump(serialize_object(record), outfile, **json_options)


def save(
    self: SObject,
    sf_client: I_SalesforceClient | None = None,
    only_changes: bool = False,
    reload_after_success: bool = False,
    external_id_field: str | None = None,
    update_only: bool = False,
):
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


def delete(
    record: _sObject,
    sf_client: I_SalesforceClient | None = None,
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
    sf_client.delete(url)
    if clear_id_field:
        delattr(record, record.attributes.id_field)


def download_file(
    record: SObject, dest: Path | None, sf_client: I_SalesforceClient | None = None
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
                    file.write(block)
            return None

        else:
            return response.read()


def reload(record: SObject, sf_client: I_SalesforceClient | None = None):
    record_id: str = getattr(record, record.attributes.id_field)
    sf_client = resolve_client(type(record), sf_client)
    reloaded = fetch(type(record), record_id, sf_client)
    record._values.update(reloaded._values)


def update_record(record: FieldConfigurableObject, /, **props):
    _fields = object_fields(type(record))
    for key, value in props.items():
        if key in _fields:
            setattr(record, key, value)


def fetch_list(
    cls: type[_sObject],
    *ids: str,
    sf_client: I_SalesforceClient | None = None,
    concurrency: int = 1,
    on_chunk_received: Callable[[Response], None] | None = None,
) -> "SObjectList[_sObject]":
    sf_client = resolve_client(cls, sf_client)

    if len(ids) == 1:
        return SObjectList(
            [fetch(cls, ids[0], sf_client)], connection=cls.attributes.connection
        )

    # pull in batches with composite API
    if concurrency > 1 and len(ids) > 2000:
        # do some async shenanigans
        return asyncio.run(
            sobject_read_async(
                cls,
                *ids,
                sf_client=sf_client.as_async,
                concurrency=concurrency,
                on_chunk_received=on_chunk_received,
            )
        )
    else:
        result: SObjectList[_sObject] = SObjectList(
            connection=cls.attributes.connection
        )
        for chunk in chunked(ids, 2000):
            response = sf_client.post(
                sf_client.composite_sobjects_url(cls.attributes.type),
                json={"ids": chunk, "fields": query_fields(cls)},
            )
            chunk_result: list[_sObject] = [cls(**record) for record in response.json()]
            result.extend(chunk_result)
            if on_chunk_received:
                on_chunk_received(response)
        return result


async def sobject_read_async(
    cls: type[_sObject],
    *ids: str,
    sf_client: I_AsyncSalesforceClient | None = None,
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
) -> type["SObject"]:
    """
    Build an SObject type definition for the named SObject based on the object 'describe' from Salesforce

    Args:
        sobject (str): The API name of the SObject in Salesforce
        connection (str): The name of the Salesforce connection to use

    Returns:
        type[SObject]: A dynamically created SObject subclass with fields matching the describe result
    """
    sf_client = sftk_client.get_connection(connection)

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
        (SObject,),
        {
            "__doc__": f"Auto-generated SObject class for {sobject} ({describe_data.label})",
            **fields,
        },
        api_name=sobject,
        connection=connection,
    )

    return sobject_class
