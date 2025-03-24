import datetime
from functools import cache
from types import NoneType
from typing import Any, Iterable, Callable
import abc
from salesforce_toolkit.client import SalesforceClient
from more_itertools import chunked

class MultiPicklistField(str):
    values: list[str]

    def __init__(self, source: str):
        self.values = source.split(";")

    def __str__(self):
        return ";".join(self.values)

class SObjectAttributes:
    type: str

class SObject:
    _sf_client_name: str = SalesforceClient.DEFAULT_CONNECTION_NAME
    _attrs: SObjectAttributes

    def __init__(self, /, ignore_extra_fields: bool = False, **kwargs):
        attrs = kwargs.pop("attributes", None)
        if attrs and attrs["type"] != self._attrs.type:
            raise TypeError(
                f"Unexpected SObject type {attrs['type']} "
                f"while deserializing {self._attrs.type} "
                f"for {type(self).__qualname__}"
            )
        for name, value in kwargs.items():
            if ignore_extra_fields and name not in self.field_annotations:
                pass
            setattr(self, name, self.deserialize_value(name, value))

    @property
    @classmethod
    @cache
    def field_annotations(cls):
        return cls.__annotations__

    def field_items(self) -> Iterable[tuple[str, Any]]:
        for field in self.field_annotations:
            yield field, getattr(self, field)


    def serialize(self) -> dict:
        return {
            name: self._serialize_value(value)
            for name, value in self.field_items()
        }

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        # assuming any dict instances are already "serialized".
        if isinstance(value, (NoneType, bool, int, float, dict)):
            return value
        elif isinstance(value, datetime.datetime):
            if value.tzinfo is None:
                value = value.astimezone()
            return value.isoformat(timespec="milliseconds")
        elif isinstance(value, datetime.date):
            return value.isoformat()
        elif isinstance(value, (list, tuple, set)):
            return [
                cls._serialize_value(nested) for nested in value
            ]
        elif _is_sobject(value):
            return value.serialize()
        else:
            raise ValueError("Unexpected Data Type")

    @classmethod
    def deserialize_value(cls, name: str, value: Any):
        datatype: type | None = cls.field_annotations.get(name)
        if datatype is None:
            raise TypeError(f"unknown field {name} on {cls.__qualname__} ({cls._attrs.type})")

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


    @property
    @classmethod
    def _client_connection(cls) -> SalesforceClient:
        return SalesforceClient.get_connection(cls._sf_client_name)

    @classmethod
    def fetch(cls, *ids: str, sf_client: SalesforceClient | None = None, concurrency: int = 1, on_chunk_received: Callable[[list["SObject"]], None]):
        if sf_client is None:
            sf_client = cls._client_connection
        if len(ids) == 1:
            # fetch single record
            sf_client.get("/")
            pass
        else:
            # pull in batches with composite API
            if concurrency > 1:
                pass
            else:
                for chunk in chunked(ids, 2000):
                    response = sf_client.get("/")
                    result = response.json(object_hook=cls)
                # do this synchronously


    @classmethod
    async def fetch_async(cls, ids: list[str], client: SalesforceClient, concurrency: int):

def _is_sobject(value):
    return isinstance(value, SObject)

def _is_sobject_subclass(cls):
    return issubclass(cls, SObject)
