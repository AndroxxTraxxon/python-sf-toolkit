import asyncio
from collections import defaultdict
from contextlib import ExitStack
import json
from pathlib import Path
from typing import (
    Any,
    Callable,
    Iterable,
    AsyncIterable,
    TypeVar,
    Coroutine,
)

from urllib.parse import quote_plus
import warnings
from httpx import Response

from .. import client as sftk_client

from more_itertools import chunked

from ..async_utils import run_concurrently
from .._models import SObjectAttributes, SObjectSaveResult
from ..interfaces import I_AsyncSalesforceClient, I_SObject, I_SalesforceClient
from .fields import (
    BlobData,
    BlobField,
    Field,
    FIELD_TYPE_LOOKUP,
    FieldConfigurableObject,
    FieldFlag,
    SObjectFieldDescribe,
)

_sObject = TypeVar("_sObject", bound=("SObject"))

_T = TypeVar("_T")


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

        # Create SObjectFieldDescribe instances for each field
        fields = [
            SObjectFieldDescribe(
                **{
                    k: v
                    for k, v in field_data.items()
                    if k in SObjectFieldDescribe._fields
                }
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
    

@staticmethod
def unflatten(flattened_data: dict[str, Any]) -> dict[str, Any]:
    inflated_data = {}
    nested_objects = defaultdict(dict)
    for fieldname in flattened_data.keys():
        if "." in fieldname:
            parent, child = fieldname.split(".", maxsplit=1)
            nested_objects[parent][child] = flattened_data[fieldname]
        else:
            inflated_data[fieldname] = flattened_data[fieldname]
    for name, nested_object in nested_objects.items():
        inflated_data[name] = unflatten(nested_object)

    return inflated_data


@staticmethod
def flatten(data: dict[str, Any]) -> dict[str, Any]:
    flattened_data = {}
    for fieldname in data.keys():
        if isinstance(fieldname, dict):
            flat_nested_data = flatten(data[fieldname])
            flattened_data.update({
                f"{fieldname}.{nested_field}" : nested_value
                for nested_field, nested_value in flat_nested_data.items()
            })
        else:
            flattened_data[fieldname] = data[fieldname]
    
    return flattened_data


class SObject(FieldConfigurableObject, I_SObject):
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
        for name, field in cls._fields.items():
            if isinstance(field, BlobField):
                assert blob_field is None, (
                    "Cannot have multiple Field/Blob fields on a single object"
                )
                blob_field = name

        if blob_field:
            del cls._fields[blob_field]
        cls.attributes = SObjectAttributes(
            api_name, connection, id_field, blob_field, tooling
        )

    def __init__(self, /, _strict_fields: bool = True, **fields):
        fields.pop("attributes", None)
        blob_value = None
        if self.attributes.blob_field:
            blob_value = fields.pop(self.attributes.blob_field, None)
        super().__init__(_strict_fields=_strict_fields, **fields)
        if self.attributes.blob_field and blob_value is not None:
            setattr(self, self.attributes.blob_field, blob_value)

    @classmethod
    def query(
        cls: type[_sObject], include_deleted: bool = False
    ) -> "SoqlQuery[_sObject]":
        """Create a new SoqlSelect query builder for this SObject type.

        Args:
            include_deleted (bool, optional): Whether to include deleted records in the query. Defaults to False.

        Returns:
            SoqlSelect: A new query builder instance for this SObject type.

        Example:
            ```python
            # Create a query builder for Contact
            query = Contact.select()

            # Add conditions and execute the query
            result = query.query()
            ```
        """
        # delayed import to avoid circular imports
        if "SoqlQuery" not in globals():
            global SoqlQuery
            from .query_builder import SoqlQuery

        return SoqlQuery(cls, include_deleted)
    
    @classmethod
    def from_file(cls, filepath: Path | str):
        ""
        if isinstance(filepath, str):
            filepath = Path(filepath).resolve()
        file_extension = filepath.suffix.lower()
        if file_extension == ".csv":
            return cls.from_csv_file(filepath)
        if file_extension == ".json":
            return cls.from_json_file(filepath)
        raise ValueError(f"Unknown file extension {file_extension}")



    @classmethod
    def from_csv_file(cls, filepath: Path | str, file_encoding="utf-8", fieldnames: list[str] | None = None):
        ""
        import csv
        if isinstance(filepath, str):
            filepath = Path(filepath).resolve()
        with filepath.open(encoding=file_encoding) as csv_file:
            reader = csv.DictReader(csv_file, fieldnames=fieldnames)
            assert reader.fieldnames, "no fieldnames found for reader."
            object_fields = set(cls.query_fields())
            for field in reader.fieldnames:
                if field not in object_fields:
                    raise KeyError(f"Field {field} in {filepath} not found for SObject {cls.__qualname__} ({cls.attributes.type})")
            return SObjectList((cls(**unflatten(row)) for row in reader), connection=cls.attributes.connection)  # type: ignore

    @classmethod
    def from_json_file(cls, filepath: Path | str, file_encoding="utf-8"):
        ""
        if isinstance(filepath, str):
            filepath = Path(filepath).resolve()
        with filepath.open(encoding=file_encoding) as csv_file:
            data = json.load(csv_file)
            if isinstance(data, list):
                return SObjectList((cls(**record) for record in data), connection=cls.attributes.connection)
            elif isinstance(data, dict):
                return SObjectList([cls(**data)], connection=cls.attributes.connection)
            raise TypeError(
                f"Unexpected {type(data).__name__} value "
                f"{str(data)[:50] + '...' if len(str(data)) > 50 else ''} "
                f"while attempting to load {cls.__qualname__} from {filepath}")

    @classmethod
    def _client_connection(cls) -> I_SalesforceClient:
        return sftk_client.SalesforceClient.get_connection(cls.attributes.connection)

    def _has_blob_content(self) -> bool:
        """
        Check if the SObject instance has any BlobFields with content set
        """
        if not self.attributes.blob_field:
            return False
        if self.attributes.blob_field in self._values:
            return True
        return False

    @classmethod
    def read(
        cls: type[_sObject],
        record_id: str,
        sf_client: I_SalesforceClient | None = None,
    ) -> _sObject:
        if sf_client is None:
            sf_client = cls._client_connection()

        if cls.attributes.tooling:
            url = f"{sf_client.tooling_sobjects_url}/{cls.attributes.type}/{record_id}"
        else:
            url = f"{sf_client.sobjects_url}/{cls.attributes.type}/{record_id}"

        fields = list(cls.keys())
        response_data = sf_client.get(url, params={"fields": ",".join(fields)}).json()

        return cls(**response_data)

    def save_insert(
        self,
        sf_client: I_SalesforceClient | None = None,
        reload_after_success: bool = False,
    ):
        if sf_client is None:
            sf_client = self._client_connection()

        # Assert that there is no ID on the record
        if _id := getattr(self, self.attributes.id_field, None):
            raise ValueError(
                f"Cannot insert record that already has an {self.attributes.id_field} set: {_id}"
            )

        # Prepare the payload with all fields
        payload = self.serialize()

        if self.attributes.tooling:
            url = f"{sf_client.tooling_sobjects_url}/{self.attributes.type}"
        else:
            url = f"{sf_client.sobjects_url}/{self.attributes.type}"

        blob_data: BlobData | None = None
        # Create a new record
        if self.attributes.blob_field and (
            blob_data := getattr(self, self.attributes.blob_field)
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
                            self.attributes.blob_field,
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
        setattr(self, self.attributes.id_field, _id_val)

        # Reload the record if requested
        if reload_after_success:
            self.reload(sf_client)

        # Clear dirty fields since we've saved
        self.dirty_fields.clear()

        return

    def save_update(
        self,
        sf_client: I_SalesforceClient | None = None,
        only_changes: bool = False,
        reload_after_success: bool = False,
        only_blob: bool = False,
    ):
        if sf_client is None:
            sf_client = self._client_connection()

        # Assert that there is an ID on the record
        if not (_id_val := getattr(self, self.attributes.id_field, None)):
            raise ValueError(f"Cannot update record without {self.attributes.id_field}")

        # If only tracking changes and there are no changes, do nothing
        if only_changes and not self.dirty_fields:
            return

        # Prepare the payload
        payload = self.serialize(only_changes)
        payload.pop(self.attributes.id_field, None)

        if self.attributes.tooling:
            url = f"{sf_client.tooling_sobjects_url}/{self.attributes.type}/{_id_val}"
        else:
            url = f"{sf_client.sobjects_url}/{self.attributes.type}/{_id_val}"

        blob_data: BlobData | None = None
        # Create a new record
        if self.attributes.blob_field and (
            blob_data := getattr(self, self.attributes.blob_field)
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
                            self.attributes.blob_field,
                            (blob_data.filename, blob_payload, blob_data.content_type),
                        ),
                    ],
                ).json()
        elif payload:
            sf_client.patch(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

        # Reload the record if requested
        if reload_after_success:
            self.reload(sf_client)

        # Clear dirty fields since we've saved
        self.dirty_fields.clear()

        return

    def save_upsert(
        self,
        external_id_field: str,
        sf_client: I_SalesforceClient | None = None,
        reload_after_success: bool = False,
        update_only: bool = False,
        only_changes: bool = False,
    ):
        if self.attributes.tooling:
            raise TypeError("Upsert is not available for Tooling SObjects.")

        if sf_client is None:
            sf_client = self._client_connection()

        # Get the external ID value
        if not (ext_id_val := getattr(self, external_id_field, None)):
            raise ValueError(
                f"Cannot upsert record without a value for external ID field: {external_id_field}"
            )

        # Encode the external ID value in the URL to handle special characters
        ext_id_val = quote_plus(str(ext_id_val))

        # Prepare the payload
        payload = self.serialize(only_changes)
        payload.pop(external_id_field, None)

        # If there's nothing to update when only_changes=True, just return
        if only_changes and not payload:
            return

        # Execute the upsert
        response = sf_client.patch(
            f"{sf_client.sobjects_url}/{self.attributes.type}/{external_id_field}/{ext_id_val}",
            json=payload,
            params={"updateOnly": update_only} if update_only else None,
            headers={"Content-Type": "application/json"},
        )

        # For an insert via upsert, the response contains the new ID
        if response.is_success:
            response_data = response.json()
            _id_val = response_data.get("id")
            if _id_val:
                setattr(self, self.attributes.id_field, _id_val)
        elif update_only and response.status_code == 404:
            raise ValueError(
                f"Record not found for external ID field {external_id_field} with value {ext_id_val}"
            )

        # Reload the record if requested
        if reload_after_success and (
            _id_val := getattr(self, self.attributes.id_field, None)
        ):
            self.reload(sf_client)

        # Clear dirty fields since we've saved
        self.dirty_fields.clear()

        return self

    def save_csv(self, filepath: Path | str, encoding="utf-8") -> None:
        import csv
        if isinstance(filepath, str):
            filepath = Path(filepath).resolve()
        with filepath.open("w+", encoding=encoding) as outfile:
            writer = csv.DictWriter(outfile, fieldnames=self.query_fields())
            writer.writeheader()
            writer.writerow(flatten(self.serialize()))

    def save_json(self, filepath: Path | str, encoding="utf-8", **json_options) -> None:
        if isinstance(filepath, str):
            filepath = Path(filepath).resolve()
        with filepath.open("w+", encoding=encoding) as outfile:
            json.dump(self.serialize(), outfile, **json_options)
        

    def save(
        self,
        sf_client: I_SalesforceClient | None = None,
        only_changes: bool = False,
        reload_after_success: bool = False,
        external_id_field: str | None = None,
        update_only: bool = False,
    ):
        # If we have an ID value, use save_update
        if getattr(self, self.attributes.id_field, None) is not None:
            return self.save_update(
                sf_client=sf_client,
                only_changes=only_changes,
                reload_after_success=reload_after_success,
            )
        # If we have an external ID field, use save_upsert
        elif external_id_field:
            return self.save_upsert(
                external_id_field=external_id_field,
                sf_client=sf_client,
                reload_after_success=reload_after_success,
                update_only=update_only,
                only_changes=only_changes,
            )
        # Otherwise, if not update_only, use save_insert
        elif not update_only:
            return self.save_insert(
                sf_client=sf_client, reload_after_success=reload_after_success
            )
        else:
            # If update_only is True and there's no ID or external ID, raise an error
            raise ValueError("Cannot update record without an ID or external ID")

    def delete(
        self, sf_client: I_SalesforceClient | None = None, clear_id_field: bool = True
    ):
        if sf_client is None:
            sf_client = self._client_connection()
        _id_val = getattr(self, self.attributes.id_field, None)

        if not _id_val:
            raise ValueError("Cannot delete unsaved record (missing ID to delete)")

        if self.attributes.tooling:
            url = f"{sf_client.tooling_sobjects_url}/{self.attributes.type}/{_id_val}"
        else:
            url = f"{sf_client.sobjects_url}/{self.attributes.type}/{_id_val}"
        sf_client.delete(url)
        if clear_id_field:
            delattr(self, self.attributes.id_field)

    def download_file(
        self, dest: Path | None, sf_client: I_SalesforceClient | None = None
    ) -> None | bytes:
        """
        Download the file associated with the blob field to the specified destination.
        https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/dome_sobject_blob_retrieve.htm

        Args:
            dest (Path | None): The destination path to save the file.
            If None, file content will be returned as bytes instead.
        """
        assert self.attributes.blob_field, "Object type must specify a blob field"
        assert not self.attributes.tooling, (
            "Cannot download file/BLOB from tooling object"
        )
        record_id = getattr(self, self.attributes.id_field, None)
        assert record_id, "Record ID cannot be None or Empty for file download"

        if sf_client is None:
            sf_client = self._client_connection()
        url = (
            f"{sf_client.sobjects_url}/{self.attributes.type}"
            f"/{record_id}/{self.attributes.blob_field}"
        )
        with sf_client.stream("GET", url) as response:
            if dest:
                with dest.open("wb") as file:
                    for block in response.iter_bytes():
                        file.write(block)
                return None

            else:
                return response.read()

    def reload(self, sf_client: I_SalesforceClient | None = None):
        record_id: str = getattr(self, self.attributes.id_field)
        if sf_client is None:
            sf_client = self._client_connection()
        reloaded = type(self).read(record_id, sf_client)
        self._values.update(reloaded._values)

    def update_values(self, /, **kwargs):
        for key, value in kwargs.items():
            if key in self.keys():
                self[key] = value

    @classmethod
    def list(
        cls: type[_sObject],
        *ids: str,
        sf_client: I_SalesforceClient | None = None,
        concurrency: int = 1,
        on_chunk_received: Callable[[Response], None] | None = None,
    ) -> "SObjectList[_sObject]":
        if sf_client is None:
            sf_client = cls._client_connection()

        if len(ids) == 1:
            return SObjectList(
                [cls.read(ids[0], sf_client)], connection=cls.attributes.connection
            )

        # pull in batches with composite API
        if concurrency > 1 and len(ids) > 2000:
            # do some async shenanigans
            return asyncio.run(
                cls.read_async(
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
                    json={"ids": chunk, "fields": list(cls.query_fields())},
                )
                chunk_result: list[_sObject] = [
                    cls(**record) for record in response.json()
                ]
                result.extend(chunk_result)
                if on_chunk_received:
                    on_chunk_received(response)
            return result

    @classmethod
    async def read_async(
        cls: type[_sObject],
        *ids: str,
        sf_client: I_AsyncSalesforceClient | None = None,
        concurrency: int = 1,
        on_chunk_received: Callable[[Response], Coroutine | None] | None = None,
    ) -> "SObjectList[_sObject]":
        if sf_client is None:
            sf_client = cls._client_connection().as_async
        async with sf_client:
            tasks = [
                sf_client.post(
                    sf_client.composite_sobjects_url(cls.attributes.type),
                    json={"ids": chunk, "fields": list(cls.query_fields())},
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

    @classmethod
    def describe(cls):
        """
        Retrieves detailed metadata information about the SObject from Salesforce.

        Returns:
            dict: The full describe result containing metadata about the SObject's
                  fields, relationships, and other properties.
        """
        sf_client = cls._client_connection()

        # Use the describe endpoint for this SObject type
        describe_url = f"{sf_client.sobjects_url}/{cls.attributes.type}/describe"

        # Make the request to get the describe metadata
        response = sf_client.get(describe_url)

        # Return the describe metadata as a dictionary
        return response.json()

    @classmethod
    def from_description(cls, sobject: str, connection: str = "") -> type["SObject"]:
        """
        Build an SObject type definition for the named SObject based on the object 'describe' from Salesforce

        Args:
            sobject (str): The API name of the SObject in Salesforce
            connection (str): The name of the Salesforce connection to use

        Returns:
            type[SObject]: A dynamically created SObject subclass with fields matching the describe result
        """
        sf_client = sftk_client.SalesforceClient.get_connection(connection)

        # Get the describe metadata for this SObject
        describe_url = f"{sf_client.sobjects_url}/{sobject}/describe"
        describe_data = SObjectDescribe.from_dict(sf_client.get(describe_url).json())

        # Extract field information
        fields = {}
        for field in describe_data.fields:
            field_name = field.name
            field_type = field.type

            field_cls: type[Field] = FIELD_TYPE_LOOKUP[field_type]
            kwargs: dict[str, Any] = {}
            flags: list[FieldFlag] = []

            if not field.updateable:
                flags.append(FieldFlag.readonly)

            fields[field_name] = field_cls(*flags, **kwargs)  # type: ignore

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

    def append(self, item):
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
            return self[0]._client_connection()
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
            if only_changes and not record.dirty_fields:
                continue
            s_record = record.serialize(only_changes)
            if include_fields:
                for fieldname in include_fields:
                    s_record[fieldname] = record._fields[fieldname].format(
                        record._values.get(fieldname)
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
        fieldnames = self[0].query_fields()
        with filepath.open("w+", encoding=encoding) as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flatten(row.serialize()) for row in self)

    def save_json(self, filepath: Path | str, encoding="utf-8", **json_options) -> None:
        if isinstance(filepath, str):
            filepath = Path(filepath).resolve()
        with filepath.open("w+", encoding=encoding) as outfile:
            json.dump([record.serialize() for record in self], outfile, **json_options)

    def save_insert(
        self, concurrency: int = 1, batch_size: int = 200, **callout_options
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
                    sf_client, record_chunks, headers, concurrency, **callout_options
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
                    json=records,
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
                            (None, json.dumps(records), "application/json"),
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
            json=records,
            headers=headers,
            **callout_options,
        )

    def save_update(
        self,
        only_changes: bool = False,
        concurrency: int = 1,
        batch_size: int = 200,
        **callout_options,
    ) -> list[SObjectSaveResult]:
        """
        Update all SObjects in the list.

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
                    headers,
                    sf_client,
                    **callout_options,
                )
            )

        # execute sync
        results: list[SObjectSaveResult] = []
        for records, blobs in record_chunks:
            assert not blobs, "Cannot update collections with files"
            response = sf_client.post(
                sf_client.composite_sobjects_url(),
                json=records,
                headers=headers,
                **callout_options,
            )
            results.extend([SObjectSaveResult(**result) for result in response.json()])

        for record, result in zip(emitted_records, results):
            if result.success:
                record.dirty_fields.clear()

        return results

    @staticmethod
    async def save_update_async(
        record_chunks: list[list[dict[str, Any]]],
        headers: dict[str, str],
        sf_client: I_SalesforceClient,
        **callout_options,
    ) -> list[SObjectSaveResult]:
        async with sf_client.as_async as a_client:
            tasks = [
                a_client.post(
                    sf_client.composite_sobjects_url(),
                    json=chunk,
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
                record.dirty_fields.clear()

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
