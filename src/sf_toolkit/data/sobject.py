# pyright: reportAny=false, reportExplicitAny=false
from abc import ABC

from typing import Any, ClassVar, NamedTuple, TypeVar
from collections.abc import Iterable, AsyncIterable
from typing_extensions import override

from ..logger import getLogger

from .._models import SObjectAttributes
from .fields import (
    BlobField,
    FieldConfigurableObject,
    object_fields,
)

_logger = getLogger("sobject")

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

    name: str
    label: str
    labelPlural: str
    keyPrefix: str
    custom: bool
    customSetting: bool
    createable: bool
    updateable: bool
    deletable: bool
    undeletable: bool
    mergeable: bool
    queryable: bool
    feedEnabled: bool
    searchable: bool
    layoutable: bool
    activateable: bool
    fields: list[SObjectFieldDescribe]
    childRelationships: list[dict[str, Any]]
    recordTypeInfos: list[dict[str, Any]]
    _raw_data: dict[str, Any]

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
        childRelationships: list[dict[str, Any]] | None = None,
        recordTypeInfos: list[dict[str, Any]] | None = None,
        **additional_properties: Any,
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
    def from_dict(cls, data: dict[str, Any]) -> "SObjectDescribe":
        """Create an SObjectDescribe instance from a dictionary (typically from a Salesforce API response)"""
        # Extract fields specifically to convert them to SObjectFieldDescribe objects
        fields_data: list[dict[str, Any]] = (
            data.pop("fields", []) if "fields" in data else []
        )
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

    def get_raw_data(self) -> dict[str, Any]:
        """Get the raw JSON data from the describe call"""
        return self._raw_data


class SObject(FieldConfigurableObject, ABC):
    attributes: ClassVar[SObjectAttributes]

    def __init_subclass__(
        cls,
        api_name: str | None = None,
        connection: str | None = None,
        id_field: str = "Id",
        tooling: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        if not api_name:
            api_name = cls.__name__
        blob_field = None
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

    def __init__(self, /, **field_values: Any):
        field_values.pop("attributes", None)
        blob_value = None
        if self.attributes.blob_field:
            blob_value = field_values.pop(self.attributes.blob_field, None)
        super().__init__(**field_values)
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


_sObject = TypeVar("_sObject", bound=SObject)


class SObjectList(list[_sObject]):
    """A list that contains SObject instances and provides bulk operations via Salesforce's composite API."""

    connection: str | None

    def __init__(
        self, iterable: Iterable[_sObject] = (), *, connection: str | None = None
    ):
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
            if not isinstance(item, SObject):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise TypeError(
                    f"All items must be SObject instances, got {type(item)}"
                )

        self.connection = connection

    @classmethod
    async def async_init(
        cls: "type[SObjectList[_sObject]]",
        a_iterable: AsyncIterable[_sObject],
        connection: str | None = None,
    ) -> "SObjectList[_sObject]":
        collected_records = [record async for record in a_iterable]
        return cls(collected_records, connection=connection)

    @override
    def append(self, item: _sObject):
        """Add an SObject to the list."""
        if not isinstance(item, SObject):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(f"Can only append SObject instances, got {type(item)}")  # pyright: ignore[reportUnreachable]
        super().append(item)  # type: ignore

    @override
    def extend(self, iterable: Iterable[_sObject]):
        """Extend the list with an iterable of SObjects."""
        if not isinstance(iterable, (tuple, list, set)):
            # ensure that we're not going to be exhausting a generator and losing items.
            iterable = tuple(iterable)
        for item in iterable:
            if not isinstance(item, SObject):  # pyright: ignore[reportUnnecessaryIsInstance]
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
