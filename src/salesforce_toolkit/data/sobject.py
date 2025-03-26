import asyncio
from collections import defaultdict
import datetime
from functools import cache
from json import JSONDecoder, JSONEncoder
from types import NoneType
from typing import Any, Iterable, Callable, NamedTuple, TypedDict, overload, TypeVar
from salesforce_toolkit.client import SalesforceClient

from more_itertools import chunked

ALL_FIELDS = "ALL FIELDS"

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


class _SObjectDict(TypedDict):
    attributes: _SObjectDictAttrs

class SObjectDecoder(JSONDecoder):
    def __init__(self, sf_connection: str = SalesforceClient.DEFAULT_CONNECTION_NAME, **kwargs):
        super().__init__(**kwargs, object_hook=self._object_hook)
        self.sf_connection = sf_connection

    def _object_hook(self, o: Any):
        if isinstance(o, dict) and (sobject_type := SObject.typeof(o, self.sf_connection)) is not None:
            return sobject_type(**o)
        return o

class SObject:
    _registry: dict[SObjectAttributes, dict[frozenset[str], type["SObject"]]] = defaultdict(dict)


    def __init_subclass__(cls, name: str, connection: str = SalesforceClient.DEFAULT_CONNECTION_NAME, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls._sf_attrs = SObjectAttributes(name, connection)
        fields = frozenset(cls.fields.keys())
        if fields in cls._registry[cls._sf_attrs]:
            raise TypeError(f"SObject Type {cls} already defined as {cls._registry[cls._sf_attrs][fields]}")
        cls._registry[cls._sf_attrs][fields] = cls

    def __init__(self, /, __strict_fields: bool = True, **fields):
        for name, value in fields.items():
            if name == "attributes":
                continue
            try:
                setattr(self, name, self.revive_value(name, value, strict=__strict_fields))
            except KeyError:
                if __strict_fields:
                    continue
                raise

    @classmethod
    def typeof(cls, record: dict, connection: str = SalesforceClient.DEFAULT_CONNECTION_NAME) -> type["SObject"] | None:
        if "attributes" not in record or "type" not in record["attributes"]:
            return None
        fields = set(record.keys())
        fields.remove("attributes")
        return cls._registry[SObjectAttributes(record["attributes"]["type"], connection)][frozenset(fields)]


    @property
    @classmethod
    @cache
    def fields(cls):
        return cls.__annotations__

    def field_items(self) -> Iterable[tuple[str, Any]]:
        for field in self.fields:
            yield field, getattr(self, field)

    @classmethod
    def revive_value(cls, name: str, value: Any, * , strict=True):
        datatype: type | None = cls.fields.get(name)
        if datatype is None:
            raise KeyError(f"unknown field {name} on {cls.__qualname__} ({cls._sf_attrs.type})")

        if isinstance(value, datatype):
            return value
        if isinstance(value, (NoneType, bool, int, float)) or isinstance(value, datatype):
            return value

        if isinstance(value, str):
            if issubclass(datatype, datetime.datetime):
                return datetime.datetime.fromisoformat(value)
            if issubclass(datatype, datetime.date):
                return datetime.date.fromisoformat(value)
            if issubclass(datatype, MultiPicklistField):
                return MultiPicklistField(value)
            raise TypeError(f"Unexpected 'str' value for {datatype.__qualname__} field {name}")

        if isinstance(value, dict):
            if _is_sobject_subclass(datatype):
                return datatype(**value)
            raise TypeError(f"Unexpected 'dict' value for {datatype.__qualname__} field {name}")

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
            params={"fields": ",".join(cls.fields)}
        ).json(object_hook=cls)


    @classmethod
    def fetch(
        cls: type[_sObject],
        *ids: str,
        sf_client: SalesforceClient | None = None,
        concurrency: int = 1,
        on_chunk_received: Callable[[list["SObject"]], None] | None = None
    ) ->  list[_sObject]:
        if sf_client is None:
            sf_client = cls._client_connection

        if len(ids) == 1:
            return [cls.get(ids[0], sf_client)]
        decoder = SObjectDecoder(sf_connection=cls._sf_attrs.connection)

        # pull in batches with composite API
        if concurrency > 1:
            # do some async shenanigans
            return asyncio.run(cls.afetch(*ids, sf_client.as_async, concurrency, on_chunk_received))
            pass
        else:
            result = []
            for chunk in chunked(ids, 2000):
                response = sf_client.get(sf_client.composite_sobjects_url)
                chunk_result: list[SObject] = decoder.decode(response.text)
                result.extend(chunk_result)
            # do this synchronously



    @classmethod
    async def afetch(
        cls: type[_sObject],
        *ids: str,
        sf_client: AsyncSalesforceClient | None = None,
        concurrency: int = 1,
        on_chunk_received: Callable[[list["SObject"]], None] | None = None
    ) -> list[_sObject]:
        if sf_client.
        async with sf_client:
            result = []
            for chunk in chunked(ids, 2000):
                response = sf_client.get(f"{sf_client.composite")
                chunk_result: list[SObject] = decoder.decode(response.text)
                result.extend(chunk_result)


    @classmethod
    def describe(cls):
        pass

def _is_sobject(value):
    return isinstance(value, SObject)

def _is_sobject_subclass(cls):
    return issubclass(cls, SObject)
