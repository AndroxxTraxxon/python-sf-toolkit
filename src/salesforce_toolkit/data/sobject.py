import asyncio
from collections import defaultdict
import datetime
from functools import cache
from json import JSONDecoder, JSONEncoder
from types import NoneType
from typing import Any, Callable, NamedTuple, TypedDict, TypeVar, Coroutine

from httpx import Response
from salesforce_toolkit.client import SalesforceClient, AsyncSalesforceClient

from more_itertools import chunked

from salesforce_toolkit.concurrency import run_with_concurrency

_sObject = TypeVar("_sObject", bound="SObject")


class MultiPicklistField(str):
    values: list[str]

    def __init__(self, source: str):
        self.values = source.split(";")

    def __str__(self):
        return ";".join(self.values)


class SObjectAttributes(NamedTuple):
    type: str
    connection: str

class SObjectFieldDescribe(NamedTuple):
    """Represents metadata about a Salesforce SObject field"""
    name: str
    label: str
    type: str
    length: int = 0
    nillable: bool = False
    picklistValues: list[dict] = []
    referenceTo: list[str] = []
    relationshipName: str | None = None
    unique: bool = False
    updateable: bool = False
    createable: bool = False
    defaultValue: Any = None
    externalId: bool = False
    autoNumber: bool = False
    calculated: bool = False
    caseSensitive: bool = False
    dependentPicklist: bool = False
    deprecatedAndHidden: bool = False
    displayLocationInDecimal: bool = False
    filterable: bool = False
    groupable: bool = False
    permissionable: bool = False
    restrictedPicklist: bool = False
    sortable: bool = False
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
        **additional_properties
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
            if not key.startswith('_'):
                self._raw_data[key] = value

    @classmethod
    def from_dict(cls, data: dict) -> 'SObjectDescribe':
        """Create an SObjectDescribe instance from a dictionary (typically from a Salesforce API response)"""
        # Extract fields specifically to convert them to SObjectFieldDescribe objects
        fields_data = data.pop('fields', []) if 'fields' in data else []

        # Create SObjectFieldDescribe instances for each field
        fields = [
            SObjectFieldDescribe(**{
                k: v for k, v in field_data.items()
                if k in SObjectFieldDescribe._fields
            })
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


class SObjectEncoder(JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, SObject):
            return self._encode_sobject(o)
        return super().default(o)

    def _encode_sobject(self, o: "SObject"):
        encoded: dict[str, Any] = {
            field_name: self._encode_sobject_field(field_name, getattr(o, field_name))
            for field_name in o.fields
        }
        encoded["attributes"] = {"type": o._sf_attrs.type}
        return encoded

    def _encode_sobject_field(self, name: str, value: Any):
        # assuming any dict instances are already "serialized".
        if isinstance(value, (NoneType, bool, int, float, dict, str)):
            return value
        elif isinstance(value, datetime.datetime):
            if value.tzinfo is None:
                value = value.astimezone()
            return value.isoformat(timespec="milliseconds")
        elif isinstance(value, datetime.date):
            return value.isoformat()
        elif isinstance(value, (list, tuple)):
            return self.default(value)
        elif isinstance(value, set):
            return self.default(list(value))
        elif isinstance(value, MultiPicklistField):
            return str(value)
        elif isinstance(value, SObject):
            return self._encode_sobject(value)
        else:
            raise ValueError("Unexpected Data Type")


class _SObjectDictAttrs(TypedDict):
    type: str
    url: str


class _SObjectDict(TypedDict):
    attributes: _SObjectDictAttrs


class SObjectDecoder(JSONDecoder):
    def __init__(
        self, sf_connection: str = SalesforceClient.DEFAULT_CONNECTION_NAME, **kwargs
    ):
        super().__init__(**kwargs, object_hook=self._object_hook)
        self.sf_connection = sf_connection

    def _object_hook(self, o: Any):
        if (
            isinstance(o, dict)
            and (sobject_type := SObject.typeof(o, self.sf_connection)) is not None
        ):
            return sobject_type(**o)
        return o


class SObject:
    _registry: dict[SObjectAttributes, dict[frozenset[str], type["SObject"]]] = (
        defaultdict(dict)
    )

    def __init_subclass__(
        cls,
        name: str,
        connection: str = SalesforceClient.DEFAULT_CONNECTION_NAME,
        **kwargs,
    ) -> None:
        super().__init_subclass__(**kwargs)
        cls._sf_attrs = SObjectAttributes(name, connection)
        fields = frozenset(cls.fields.keys())
        if fields in cls._registry[cls._sf_attrs]:
            raise TypeError(
                f"SObject Type {cls} already defined as {cls._registry[cls._sf_attrs][fields]}"
            )
        cls._registry[cls._sf_attrs][fields] = cls

    def __init__(self, /, __strict_fields: bool = True, **fields):
        for name, value in fields.items():
            if name == "attributes":
                continue
            try:
                setattr(
                    self, name, self.revive_value(name, value, strict=__strict_fields)
                )
            except KeyError:
                if __strict_fields:
                    continue
                raise

    @classmethod
    def typeof(
        cls, record: dict, connection: str = SalesforceClient.DEFAULT_CONNECTION_NAME
    ) -> type["SObject"] | None:
        if "attributes" not in record or "type" not in record["attributes"]:
            return None
        fields = set(record.keys())
        fields.remove("attributes")
        return cls._registry[
            SObjectAttributes(record["attributes"]["type"], connection)
        ].get(frozenset(fields))


    @property
    @classmethod
    @cache
    def fields(cls):
        return cls.__annotations__

    @classmethod
    def keys(cls):
        return cls.__annotations__.keys()

    def __getitem__(self, name):
        if name not in self.keys():
            raise KeyError("Undefined field " + name)
        return getattr(self, name)

    @classmethod
    def revive_value(cls, name: str, value: Any, *, strict=True):
        datatype: type | None = cls.fields.get(name)
        if datatype is None:
            if strict:
                raise KeyError(
                    f"unknown field {name} on {cls.__qualname__} ({cls._sf_attrs.type})"
                )
            return value

        if isinstance(value, datatype):
            return value

        if isinstance(value, (NoneType, bool, int, float)) or isinstance(
            value, datatype
        ):
            return value

        if isinstance(value, str):
            if issubclass(datatype, datetime.datetime):
                return datetime.datetime.fromisoformat(value)
            if issubclass(datatype, datetime.date):
                return datetime.date.fromisoformat(value)
            if issubclass(datatype, MultiPicklistField):
                return MultiPicklistField(value)

        elif isinstance(value, dict):
            if _is_sobject_subclass(datatype):
                return datatype(**value)
            raise TypeError(
                f"Unexpected 'dict' value for {datatype.__qualname__} field {name}"
            )

        raise TypeError("Unexpected ")

    @property
    @classmethod
    def _client_connection(cls) -> SalesforceClient:
        return SalesforceClient.get_connection(cls._sf_attrs.connection)

    @classmethod
    def get(
        cls: type[_sObject],
        record_id: str,
        sf_client: SalesforceClient | None = None,
    ) -> _sObject:
        if sf_client is None:
            sf_client = cls._client_connection

        # fetch single record
        return sf_client.get(
            f"{sf_client.sobjects_url}/{cls._sf_attrs.type}/{record_id}",
            params={"fields": ",".join(cls.fields)},
        ).json(object_hook=cls)

    @classmethod
    def fetch(
        cls: type[_sObject],
        *ids: str,
        sf_client: SalesforceClient | None = None,
        concurrency: int = 1,
        on_chunk_received: Callable[[Response], None] | None = None,
    ) -> list[_sObject]:
        if sf_client is None:
            sf_client = cls._client_connection

        if len(ids) == 1:
            return [cls.get(ids[0], sf_client)]
        decoder = SObjectDecoder(sf_connection=cls._sf_attrs.connection)

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
                    sf_client.composite_sobjects_url(cls._sf_attrs.type),
                    json={"ids": chunk, "fields": list(cls.fields)},
                )
                chunk_result: list[_sObject] = decoder.decode(response.text)
                result.extend(chunk_result)
                if on_chunk_received:
                    on_chunk_received(response)
            return result

    @classmethod
    async def afetch(
        cls: type[_sObject],
        *ids: str,
        sf_client: AsyncSalesforceClient | None = None,
        concurrency: int = 1,
        on_chunk_received: Callable[[Response], Coroutine | None] | None = None,
    ) -> list[_sObject]:
        if sf_client is None:
            sf_client =cls._client_connection.as_async
        async with sf_client:
            tasks = [
                sf_client.post(
                    sf_client.composite_sobjects_url(cls._sf_attrs.type),
                    json={"ids": chunk, "fields": list(cls.fields)},
                )
                for chunk in chunked(ids, 2000)
            ]
            decoder = SObjectDecoder(sf_connection=cls._sf_attrs.connection)
            return [
                item
                for response in (
                    await run_with_concurrency(concurrency, tasks, on_chunk_received)
                )
                for item in decoder.decode(response.text)
            ]

    @classmethod
    def describe(cls):
        """
        Retrieves detailed metadata information about the SObject from Salesforce.

        Returns:
            dict: The full describe result containing metadata about the SObject's
                  fields, relationships, and other properties.
        """
        sf_client = cls._client_connection

        # Use the describe endpoint for this SObject type
        describe_url = f"{sf_client.sobjects_url}/{cls._sf_attrs.type}/describe"

        # Make the request to get the describe metadata
        response = sf_client.get(describe_url)

        # Return the describe metadata as a dictionary
        return response.json()

    @classmethod
    def from_description(cls, sobject: str, connection: str = SalesforceClient.DEFAULT_CONNECTION_NAME) -> type["SObject"]:
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
        field_annotations = {}
        for field in describe_data.fields:
            field_name = field.name
            field_type = field.type

            # Map Salesforce field types to Python types
            python_type = str  # Default type
            if field_type == 'boolean':
                python_type = bool
            elif field_type in ('int', 'double', 'currency', 'percent'):
                python_type = float
            elif field_type == 'date':
                python_type = datetime.date
            elif field_type == 'datetime':
                python_type = datetime.datetime
            elif field_type == 'time':
                python_type = datetime.time
            elif field_type == 'multipicklist':
                python_type = MultiPicklistField

            field_annotations[field_name] = python_type

        # Create a new SObject subclass
        sobject_class: type[_sObject] = type(  # type: ignore
            f"{sobject.title().replace('__c', '').replace('_', '')}SObject",
            (SObject,),
            {
                "__annotations__": field_annotations,
                "__doc__": f"Auto-generated SObject class for {sobject} ({describe_data.label})"
            },
            name=sobject,
            connection=connection
        )

        return sobject_class




def _is_sobject(value):
    return isinstance(value, SObject)


def _is_sobject_subclass(cls):
    return issubclass(cls, SObject)
