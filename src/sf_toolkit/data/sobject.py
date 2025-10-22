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

    def assert_single_type(self):
        """Assert there is exactly one type of record in the list"""
        assert len(self) > 0, "There must be at least one record."
        record_type = type(self[0])
        assert all(isinstance(record, record_type) for record in self), (
            "Records must be of the same type."
        )
