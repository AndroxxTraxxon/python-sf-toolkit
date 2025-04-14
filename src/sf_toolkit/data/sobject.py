import asyncio
from collections import defaultdict
from typing import (
    Callable,
    TypeVar,
    Coroutine,
)

from urllib.parse import quote_plus
from httpx import Response
from .. import client as sftk_client

from more_itertools import chunked

from ..concurrency import run_concurrently
from .._models import SObjectAttributes
from ..interfaces import I_AsyncSalesforceClient, I_SObject, I_SalesforceClient
from .fields import FIELD_TYPE_LOOKUP, FieldConfigurableObject, FieldFlag, SObjectFieldDescribe
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


class SObject(FieldConfigurableObject, I_SObject):
    _registry: dict[SObjectAttributes, dict[frozenset[str], type["SObject"]]] = (
        defaultdict(dict)
    )

    def __init_subclass__(
        cls,
        api_name: str | None = None,
        connection: str = "",
        id_field: str = "Id",
        **kwargs,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if not api_name:
            api_name = cls.__name__
        connection = connection or I_SalesforceClient.DEFAULT_CONNECTION_NAME
        cls.attributes = SObjectAttributes(api_name, connection, id_field)
        cls._register_()


    @classmethod
    def _register_(cls):
        fields = frozenset(cls.keys())
        if fields in cls._registry[cls.attributes]:
            raise TypeError(
                f"SObject Type {cls} already defined as {cls._registry[cls.attributes][fields]}"
            )
        cls._registry[cls.attributes][fields] = cls

    @classmethod
    def _unregister_(cls):
        fields = frozenset(cls.keys())
        sobject_registry = cls._registry[cls.attributes]
        if fields in sobject_registry and sobject_registry[fields] is cls:
            del sobject_registry[fields]
            # Remove the entire entry if there are no more classes for this SObject type
            if not sobject_registry:
                del cls._registry[cls.attributes]

    def __init__(self, /, __strict_fields: bool = True, **fields):
        super().__init__()
        for name, value in fields.items():
            if name == "attributes":
                continue
            try:
                if name not in self.keys():
                    raise KeyError(
                        f"Field {name} not defined for {type(self).__qualname__}"
                    )
                setattr(
                    self, name, value
                )
            except KeyError:
                if __strict_fields:
                    continue
                raise
        self.dirty_fields.clear()


    @classmethod
    def typeof(
        cls, record: dict, connection: str = "", id_field: str = "Id"
    ) -> type["SObject"] | None:
        if "attributes" not in record or "type" not in record["attributes"]:
            return None
        fields = set(record.keys())
        fields.remove("attributes")
        return cls._registry[
            SObjectAttributes(
                record["attributes"]["type"],
                connection or sftk_client.SalesforceClient.DEFAULT_CONNECTION_NAME,
                id_field,
            )
        ].get(frozenset(fields))

    @classmethod
    def _client_connection(cls) -> I_SalesforceClient:
        return sftk_client.SalesforceClient.get_connection(cls.attributes.connection)

    @classmethod
    def read(
        cls: type[_sObject],
        record_id: str ,
        sf_client: I_SalesforceClient | None = None,
    ) -> _sObject:
        if sf_client is None:
            sf_client = cls._client_connection()
        response_data = sf_client.get(
            f"{sf_client.sobjects_url}/{cls.attributes.type}/{record_id}",
            params={"fields": ",".join(cls.keys())},
        ).json()

        # fetch single record
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

        # Create a new record
        response_data = sf_client.post(
            f"{sf_client.sobjects_url}/{self.attributes.type}",
            json=payload,
            headers={"Content-Type": "application/json"},
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

        # Update the record if there's anything to update
        if payload:
            sf_client.patch(
                f"{sf_client.sobjects_url}/{self.attributes.type}/{_id_val}",
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

    def save(
        self,
        sf_client: I_SalesforceClient | None = None,
        only_changes: bool = False,
        reload_after_success: bool = False,
        external_id_field: str | None = None,
        update_only: bool = False,
    ):
        # If we have an ID value, use save_update
        if (_id_value := getattr(self, self.attributes.id_field, None)) is not None:
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

        sf_client.delete(
            f"{sf_client.sobjects_url}/{self.attributes.type}/{_id_val}",
        )
        if clear_id_field:
            delattr(self, self.attributes.id_field)

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
    ) -> list[_sObject]:
        if sf_client is None:
            sf_client = cls._client_connection()

        if len(ids) == 1:
            return [cls.read(ids[0], sf_client)]
        # decoder = SObjectDecoder(sf_connection=cls._sf_attrs.connection)

        # pull in batches with composite API
        if concurrency > 1:
            # do some async shenanigans
            return asyncio.run(
                cls.afetch(
                    *ids,
                    sf_client=sf_client.as_async,
                    concurrency=concurrency,
                    on_chunk_received=on_chunk_received,
                )
            )
        else:
            result = []
            for chunk in chunked(ids, 2000):
                response = sf_client.post(
                    sf_client.composite_sobjects_url(cls.attributes.type),
                    json={"ids": chunk, "fields": list(cls.keys())},
                )
                chunk_result: list[_sObject] = [
                    cls(**record) for record in response.json()
                ]
                result.extend(chunk_result)
                if on_chunk_received:
                    on_chunk_received(response)
            return result

    @classmethod
    async def afetch(
        cls: type[_sObject],
        *ids: str,
        sf_client: I_AsyncSalesforceClient | None = None,
        concurrency: int = 1,
        on_chunk_received: Callable[[Response], Coroutine | None] | None = None,
    ):
        if sf_client is None:
            sf_client = cls._client_connection().as_async
        async with sf_client:
            tasks = [
                sf_client.post(
                    sf_client.composite_sobjects_url(cls.attributes.type),
                    json={"ids": chunk, "fields": list(cls.keys())},
                )
                for chunk in chunked(ids, 2000)
            ]
            records: list[_sObject] = [  # type: ignore
                cls(**record)
                for response in (
                    await run_concurrently(concurrency, tasks, on_chunk_received)
                )
                for record in response.json()
            ]
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

            field_cls = FIELD_TYPE_LOOKUP[field_type]
            kwargs = {}
            flags = []

            if not field.updateable:
                flags.append(FieldFlag.readonly)

            fields[field_name] = field_cls(*flags, **kwargs)

        # Create a new SObject subclass
        sobject_class: type[_sObject] = type(  # type: ignore
            f"SObject__{sobject}",
            (SObject,),
            {
                "__doc__": f"Auto-generated SObject class for {sobject} ({describe_data.label})",
                **fields
            },
            api_name=sobject,
            connection=connection,
        )

        return sobject_class


def _is_sobject(value):
    return isinstance(value, SObject)


def _is_sobject_subclass(cls):
    return issubclass(cls, SObject)
