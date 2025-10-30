"""
Module for basic field and field-configurable object scaffolding
"""
# pyright: basic

from collections import defaultdict
from collections.abc import Mapping
import datetime
from enum import Flag, auto
import typing
import io
from pathlib import Path
from sf_toolkit.logger import getLogger
from typing_extensions import override
import warnings

from httpx._types import FileContent  # type: ignore

T = typing.TypeVar("T")
U = typing.TypeVar("U")
_LOGGER = getLogger("data")


class ReadOnlyAssignmentException(TypeError):
    """Exception for when value assignments are performed on readonly fields"""


class MultiPicklistValue(str):
    """type for semicolon-delimited multi-value attributes"""

    values: list[str]

    def __init__(self, source: str):
        self.values = (source and source.split(";")) or []

    @override
    def __str__(self):
        return ";".join(self.values)


class FieldFlag(Flag):
    """Flags to describe the allowed functionality on defined fields"""

    nillable = auto()
    unique = auto()
    readonly = auto()
    case_sensitive = auto()
    updateable = auto()
    createable = auto()
    calculated = auto()
    filterable = auto()
    sortable = auto()
    groupable = auto()
    permissionable = auto()
    restricted_picklist = auto()
    display_location_in_decimal = auto()
    write_requires_master_read = auto()


class FieldConfigurableObject:
    """
    Base object to be extended with Field definitions.
    """

    _fields: typing.ClassVar[dict[str, "Field[type[typing.Any]]"]]
    _strict_fields: typing.ClassVar[bool] = False

    _values: dict[str, typing.Any]
    _dirty_fields: set[str]

    def __init__(
        self,
        **field_values: typing.Any,
    ):
        self._values = {}
        _fields = object_fields(type(self))
        self._dirty_fields = set()
        for field, value in field_values.items():
            if field not in _fields:
                message = f"Field {field} not defined for {type(self).__qualname__}"
                if type(self)._strict_fields:
                    raise KeyError(message)
                else:
                    warnings.warn(message)
            setattr(self, field, value)
        for field_name, field in _fields.items():
            if (
                field_name not in field_values
                and (_default := field.default) is not None
            ):
                # set default values for fields not provided
                if (
                    callable(field.default)
                    and field.meta_py_type
                    and not isinstance(field.default, field.meta_py_type)
                ):
                    # if a method/function/lambda is passed, call that to get default value
                    _default = field.default()
                setattr(self, field_name, _default)
        dirty_fields(self).clear()

    def __init_subclass__(cls, strict_fields: bool = False) -> None:
        cls_fields = object_fields(cls)
        for parent in cls.__mro__:
            if (
                issubclass(parent, FieldConfigurableObject)
                and parent is not FieldConfigurableObject
            ):
                parent_fields = object_fields(parent)
                for field, fieldtype in parent_fields.items():
                    if field not in cls_fields:
                        cls_fields[field] = fieldtype
        cls._strict_fields = strict_fields

    def __getitem__(self, name: str):
        value = getattr(self, name, None)
        if value is None and name not in object_fields(type(self)):
            raise KeyError(f"Undefined field {name} on object {type(self)}")
        return value

    def __setitem__(self, name: str, value: typing.Any):
        if name not in object_fields(type(self)):
            raise KeyError(f"Undefined field {name} on object {type(self)}")
        setattr(self, name, value)

    @override
    def __delattr__(self, name: str, /) -> None:
        if name not in object_fields(type(self)):
            raise KeyError(f"Undefined field {name} on object {type(self)}")
        if name in self._values:
            del self._values[name]

    def __delitem__(self, name: str):
        self.__delattr__(name)


_field_map: dict[type[FieldConfigurableObject], dict[str, "Field[typing.Any]"]] = (
    defaultdict(dict)
)


def object_fields(
    cls: type[FieldConfigurableObject],
) -> dict[str, "Field[typing.Any]"]:
    """
    returns the dictionary of field name to Field instances
    configured on this class
    """
    return _field_map[cls]


def object_values(rec: FieldConfigurableObject) -> Mapping[str, typing.Any]:
    """
    returns the dictionary of field name to current value
    configured on this object instance
    """
    return {name: getattr(rec, name, None) for name in object_fields(type(rec))}


def query_fields(cls: type[FieldConfigurableObject]) -> list[str]:
    """
    returns the list of fully qualified fields as they would
    need to appear in a SOQL query
    """
    fields: list[str] = list()
    for field, fieldtype in object_fields(cls).items():
        if (
            isinstance(fieldtype, ReferenceField)
            and fieldtype.meta_py_type is not None
            and issubclass(fieldtype.meta_py_type, FieldConfigurableObject)
        ):
            fields.extend(
                [
                    field + "." + subfield
                    for subfield in query_fields(fieldtype.meta_py_type)
                ]
            )
        else:
            fields.append(field)
    return fields


def dirty_fields(rec: FieldConfigurableObject) -> set[str]:
    """
    Returns the set of fields that have been modified since the last
    time this object was `.save()`-d to Salesforce
    """
    _dirty: set[str] | None = getattr(rec, "_dirty_fields", None)
    if _dirty is None:
        _dirty = set()
        setattr(rec, "_dirty_fields", _dirty)
    return _dirty


def serialize_object(
    record: FieldConfigurableObject,
    only_changes: bool = False,
    all_fields: bool = False,
):
    """
    Serialize this record to standard python types (dict, list, str, etc.)
    for easier transport
    with file formats like JSON, YAML
    """
    assert not (only_changes and all_fields), (
        "Cannot serialize both only changes and all fields."
    )
    values = object_values(record)
    fields = object_fields(type(record))
    if all_fields:
        return {
            name: field.format(values.get(name, None)) for name, field in fields.items()
        }

    if only_changes:
        return {
            name: field.format(value)
            for name, value in values.items()
            if (field := fields[name])
            and name in dirty_fields(record)
            and FieldFlag.readonly not in field.flags
        }

    return {
        name: field.format(value)
        for name, value in record._values.items()
        if (field := fields[name]) and FieldFlag.readonly not in field.flags
    }


_FCO_Type = typing.TypeVar("_FCO_Type", bound=FieldConfigurableObject)


class FieldProps(typing.Generic[T], typing.TypedDict):
    default: typing.NotRequired[T | typing.Callable[[], T] | None]


class Field(typing.Generic[T]):
    """
    Base class for all configurable field types
    """

    _owner: type
    _py_type: type[T] | None = None
    _name: str
    flags: set[FieldFlag]
    default: T | typing.Callable[[], T] | None

    def __init__(
        self, *flags: FieldFlag, py_type: type[T], **props: typing.Unpack[FieldProps[T]]
    ):
        self._py_type = py_type
        self.flags = set(flags)
        self._owner = type(None)
        self._name = ""
        if (default := props.pop("default", None)) is not None:
            assert isinstance(default, py_type) or callable(default), (
                f"default value must be of type {py_type}"
                f" or a callable generating {py_type}"
            )
        self.default = default

    # Add descriptor protocol methods
    def __get__(self, obj: FieldConfigurableObject, objtype=None) -> T:
        return obj._values.get(self._name)  # pyright: ignore[reportPrivateUsage, reportReturnType]

    def __set__(self, obj: FieldConfigurableObject, value: typing.Any):
        value = self.revive(value)
        self.validate(value)
        if FieldFlag.readonly in self.flags and self._name in obj._values:
            raise ReadOnlyAssignmentException(
                f"Field {self._name} is readonly on object {self._owner.__name__}"
            )
        obj._values[self._name] = value
        dirty_fields(obj).add(self._name)

    def __repr__(self):
        return f"<{type(self).__name__} {self._owner.__name__}.{self._name}>"

    @property
    def meta_py_type(self) -> type[T] | None:
        """Get the configured underlying Python type of this field's content"""
        return self._py_type

    def revive(self, value: typing.Any) -> T | None:
        """
        Attempts to "revive" value to be assigned to this field
        into a more useful type.
        """
        return value

    def format(self, value: T) -> typing.Any:
        """
        Formats the value contained in this field
        into a more serializeable format.
        """
        return value

    def __set_name__(self, cls: type[FieldConfigurableObject], name):
        """Lifecycle hook implicitly called"""
        self._owner = cls
        self._name = name
        object_fields(cls)[name] = self

    def __delete__(self, obj: FieldConfigurableObject):
        del obj._values[self._name]
        if hasattr(obj, "_dirty_fields"):
            dirty_fields(obj).discard(self._name)

    def validate(self, value):
        """Validates the revived value passed to the field"""
        if value is None:
            return
        if self._py_type is not None and not isinstance(value, self._py_type):
            raise TypeError(
                f"Expected {self._py_type.__qualname__} for field {self._name} "
                f"on {self._owner.__name__}, got {type(value).__name__} {str(value)[:50]}"
            )


class RawField(Field[typing.Any]):
    """
    A Field that does no transformation or validation on the values passed to it.
    """

    def __init__(
        self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[typing.Any]]
    ):
        super().__init__(*flags, py_type=object, **props)

    @override
    def validate(self, value):
        return


class TextField(Field[str]):
    """
    A field to contain text or string values
    """

    def __init__(self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[str]]):
        super().__init__(*flags, py_type=str, **props)


class IdField(TextField):
    """
    A field to contain 15- or 18-character alphanumeric Id
    Strings used by Salesforce
    """

    @override
    def validate(self, value: str):
        if value is None:
            return
        message = f" '{value}' is not a valid Salesforce Id. "
        assert isinstance(value, str), message + "Expected a string."
        assert len(value) in (
            15,
            18,
        ), message + f"Expected a string of length 15 or 18, found {len(value)}"
        assert value.isalnum(), message + "Expected strictly alphanumeric characters."


class PicklistField(TextField):
    """
    A field to contain text values chosen from a pre-configured list.
    """

    _options_: list[str]

    def __init__(
        self,
        *flags: FieldFlag,
        options: list[str] | None = None,
        **props: typing.Unpack[FieldProps[str]],
    ):
        super().__init__(*flags, **props)
        self._options_ = options or []
        if (default_value := props.get("default", None)) is not None:
            if (
                options
                and isinstance(default_value, str)
                and default_value not in options
            ):
                raise ValueError(
                    (
                        f"Default value '{default_value}' is not in configured values for field"
                        f" {self._name}"
                    )
                )

    @override
    def validate(self, value: str):
        if self._options_ and value not in self._options_:
            raise ValueError(
                (
                    f"Selection '{value}' is not in "
                    f"configured values for field {self._name}"
                )
            )


class MultiPicklistField(Field[MultiPicklistValue]):
    """
    A field to contain text values (optionally more than one)
    chosen from a pre-configured list
    """

    _options_: list[str]

    def __init__(
        self,
        *flags: FieldFlag,
        options: list[str] | None = None,
        **props: typing.Unpack[FieldProps[MultiPicklistValue]],
    ):
        super().__init__(*flags, py_type=MultiPicklistValue, **props)
        if (default_value := props.get("default", None)) is not None:
            if isinstance(default_value, str):
                default_value = props["default"] = MultiPicklistValue(default_value)
            if options and isinstance(default_value, MultiPicklistValue):
                for value in default_value.values:
                    if value not in options:
                        raise ValueError(
                            (
                                f"Default value '{value}' is not in configured values for field"
                                f" {self._name}"
                            )
                        )

        self._options_ = options or []

    @override
    def revive(self, value: str):
        return MultiPicklistValue(value)

    @override
    def validate(self, value: MultiPicklistValue):
        for item in value.values:
            if self._options_ and item not in self._options_:
                raise ValueError(
                    f"Selection '{item}' is not in configured values for {self._name}"
                )


class NumberField(Field[float]):
    """
    A field to contain a floating-point numeric value.
    """

    def __init__(self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[float]]):
        super().__init__(*flags, py_type=float, **props)

    @override
    def revive(self, value: typing.Any):
        return None if value is None else float(value)


class IntField(Field[int]):
    """
    A field to contain an integer numeric value.
    """

    def __init__(self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[int]]):
        super().__init__(*flags, py_type=int, **props)

    @override
    def revive(self, value: typing.Any):
        return None if value is None else int(value)


class CheckboxField(Field[bool]):
    """
    A field to contain a boolean value.
    """

    def __init__(self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[bool]]):
        super().__init__(*flags, py_type=bool, **props)

    @override
    def revive(self, value: typing.Any):
        return None if value is None else bool(value)


class DateField(Field[datetime.date]):
    """
    A field to contain a date value.
    """

    def __init__(
        self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[datetime.date]]
    ):
        super().__init__(*flags, py_type=datetime.date, **props)

    @override
    def revive(self, value: typing.Any):
        if value is None or isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(value)

    @override
    def format(self, value: datetime.date | None):
        if value:
            return value.isoformat()
        return None


class TimeField(Field[datetime.time]):
    """
    A field to contain a time value.
    """

    def __init__(
        self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[datetime.time]]
    ):
        super().__init__(*flags, py_type=datetime.time, **props)

    @override
    def format(self, value: datetime.time | None):
        if value is None:
            return None
        return value.isoformat(timespec="milliseconds")

    @override
    def revive(self, value: typing.Any):
        if value:
            return datetime.time.fromisoformat(str(value))
        return None


class DateTimeField(Field[datetime.datetime]):
    """
    A field to contain a datetime value.
    """

    def __init__(
        self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[datetime.datetime]]
    ):
        super().__init__(*flags, py_type=datetime.datetime, **props)

    @override
    def revive(self, value: str | None):
        if value is None:
            return None
        return datetime.datetime.fromisoformat(str(value))

    @override
    def format(self, value: datetime.datetime) -> str:
        if value.tzinfo is None:
            value = value.astimezone()
        return value.isoformat(timespec="milliseconds")


class ReferenceField(Field[_FCO_Type]):
    """
    A field to contain a nested field configurable object,
    typically represented in Salesforce as a lookup or master-detail relationship
    """

    @override
    def revive(self, value: typing.Any):  # pyright: ignore[reportIncompatibleMethodOverride]
        if value is None:
            return None
        assert self._py_type is not None
        if isinstance(value, self._py_type):
            return value
        if isinstance(value, dict):
            return self._py_type(**value)

    @override
    def format(self, value: _FCO_Type) -> dict[str, typing.Any] | _FCO_Type:
        try:
            return serialize_object(value)
        except AttributeError:
            _LOGGER.warning(
                f"Unable to format value for field {self._owner.__qualname__}.{self._name}: {str(value)}"
            )
            return value


class ListField(Field[list[_FCO_Type]]):
    """
    A field to contain a nested list of field configurable object,
    typically represented in Salesforce as a lookup or master-detail relationship
    """

    _nested_type: type[_FCO_Type | typing.Any]

    def __init__(
        self,
        item_type: type[_FCO_Type | typing.Any],
        *flags: FieldFlag,
        **props: typing.Unpack[FieldProps[list[_FCO_Type]]],
    ):
        self._nested_type = item_type
        super().__init__(*flags, py_type=list, **props)

        try:
            global SObjectList, SObject
            # ensure SObjectList is imported
            # at the time of SObject type/class definition
            _ = SObjectList
        except NameError:
            from .sobject import SObjectList, SObject

    def revive(
        self,
        value: list[dict[str, typing.Any] | _FCO_Type] | dict[str, typing.Any] | None,
    ):  # type: ignore
        if value is None:
            return None
        if isinstance(value, SObjectList):
            return value
        if isinstance(value, list):
            if issubclass(self._nested_type, SObject):
                return SObjectList(  # type: ignore
                    (
                        self._nested_type(**object_values(item))
                        if isinstance(item, SObject)
                        else self._nested_type(**item)
                        for item in value
                    )
                )  # type: ignore
            else:
                return value
        if isinstance(value, dict):
            # assume the dict is a QueryResult-formatted dictionary

            if issubclass(self._nested_type, SObject):
                return SObjectList(
                    [self._nested_type(**item) for item in value["records"]]
                )  # type: ignore
            return list(value.items())
        raise TypeError(
            f"Unexpected type {type(value)} for {type(self).__name__}[{self._nested_type.__name__}]"
        )


class BlobData:
    """Class to represent blob data that will be uploaded to Salesforce"""

    _filepointer: io.IOBase | None = None

    def __init__(
        self,
        data: typing.Union[str, bytes, Path, io.IOBase],
        filename: str | None = None,
        content_type: str | None = None,
        **props: typing.Unpack[FieldProps[datetime.date]],
    ):
        self.data = data
        self.filename = filename
        self.content_type = content_type

        # Determine filename if not provided
        if self.filename is None:
            if isinstance(data, Path):
                self.filename = data.name

        # Determine content type if not provided
        if self.content_type is None:
            if self.filename and "." in self.filename:
                ext = self.filename.split(".")[-1].lower()
                if ext in ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"]:
                    self.content_type = f"application/{ext}"
                elif ext in ["jpg", "jpeg", "png", "gif"]:
                    self.content_type = f"image/{ext}"
                else:
                    self.content_type = "application/octet-stream"
            else:
                self.content_type = "application/octet-stream"

    def __enter__(self) -> FileContent:
        """Get the binary content of the blob data"""
        if isinstance(self.data, str):
            return self.data.encode("utf-8")
        elif isinstance(self.data, bytes):
            return self.data
        elif isinstance(self.data, Path):
            self._filepointer = self.data.open()
            with open(self.data, "rb") as f:
                return f.read()
        elif isinstance(self.data, io.IOBase):  #  pyright: ignore[reportUnnecessaryIsInstance]
            # Reset the file pointer if it's a file object
            if hasattr(self.data, "seek"):
                self.data.seek(0)
            return self.data.read()
        else:
            raise TypeError(f"Unsupported data type: {type(self.data)}")

    def __exit__(self, exc_type, exc_value, traceback):
        if self._filepointer:
            self._filepointer.close()


class GeolocationSerialized(typing.TypedDict):
    latitude: float
    longitude: float


class Geolocation(typing.NamedTuple):
    latitude: float
    longitude: float


class GeolocationField(Field[Geolocation]):
    """Field type for handling geolocation data in Salesforce"""

    def __init__(
        self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[Geolocation]]
    ):
        super().__init__(*flags, py_type=Geolocation, **props)

    @override
    def revive(self, value: Geolocation | GeolocationSerialized | None):
        if value is None:
            return None
        if isinstance(value, Geolocation):
            return value
        if isinstance(value, dict):
            return Geolocation(
                latitude=value.get("latitude"), longitude=value.get("longitude")
            )
        raise TypeError(f"Cannot revive value of type {type(value)} to Geolocation")

    @override
    def format(self, value):
        if value is None:
            return None
        return {"latitude": value.latitude, "longitude": value.longitude}


class AddressSerialized(typing.TypedDict):
    Accuracy: typing.NotRequired[str]
    City: typing.NotRequired[str]
    Country: typing.NotRequired[str]
    CountryCode: typing.NotRequired[str]
    Latitude: typing.NotRequired[float]
    Longitude: typing.NotRequired[float]
    PostalCode: typing.NotRequired[str]
    State: typing.NotRequired[str]
    StateCode: typing.NotRequired[str]
    Street: typing.NotRequired[str]


class Address(typing.NamedTuple):
    Accuracy: str | None = None
    City: str | None = None
    Country: str | None = None
    CountryCode: str | None = None
    Latitude: float | None = None
    Longitude: float | None = None
    PostalCode: str | None = None
    State: str | None = None
    StateCode: str | None = None
    Street: str | None = None


class AddressField(Field[Address]):
    """
    Field type for handling address data in Salesforce
    """

    def __init__(self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[Address]]):
        super().__init__(*flags, py_type=Address, **props)

    @override
    def revive(self, value: Address | AddressSerialized | None):
        if value is None:
            return None
        if isinstance(value, Address):
            return value
        if isinstance(value, dict):
            return Address(
                Accuracy=value.get("Accuracy"),
                City=value.get("City"),
                Country=value.get("Country"),
                CountryCode=value.get("CountryCode"),
                Latitude=value.get("Latitude"),
                Longitude=value.get("Longitude"),
                PostalCode=value.get("PostalCode"),
                State=value.get("State"),
                StateCode=value.get("StateCode"),
                Street=value.get("Street"),
            )
        raise TypeError(f"Cannot revive value of type {type(value)} to Address")

    @override
    def format(self, value: Address | None):
        if value is None:
            return None
        return {
            "Accuracy": value.Accuracy,
            "City": value.City,
            "Country": value.Country,
            "CountryCode": value.CountryCode,
            "Latitude": value.Latitude,
            "Longitude": value.Longitude,
            "PostalCode": value.PostalCode,
            "State": value.State,
            "StateCode": value.StateCode,
            "Street": value.Street,
        }


class BlobField(Field[BlobData]):
    """Field type for handling blob data in Salesforce"""

    def __init__(self, *flags: FieldFlag, **props: typing.Unpack[FieldProps[BlobData]]):
        super().__init__(*flags, py_type=BlobData, **props)

    def revive(self, value):
        if value is None:
            return None
        if isinstance(value, BlobData):
            return value
        # Convert different input types to BlobData
        return BlobData(value)

    def format(self, value):
        # This is a special case - BlobFields are not included in the JSON payload
        # They are handled specially when uploading via multipart/form-data
        return None

    # Add descriptor protocol methods
    def __get__(self, obj: FieldConfigurableObject, objtype=None) -> BlobData:
        if obj is None:
            return self
        return getattr(obj, self._name + "_BlobData", None)  # type: ignore

    def __set__(self, obj: FieldConfigurableObject, value: typing.Any):
        value = self.revive(value)
        self.validate(value)
        if FieldFlag.readonly in self.flags and self._name in obj._values:
            raise ReadOnlyAssignmentException(
                f"Field {self._name} is readonly on object {self._owner.__name__}"
            )
        setattr(obj, self._name + "_BlobData", value)
        dirty_fields(obj).add(self._name)


FIELD_TYPE_LOOKUP: dict[str, type[Field[typing.Any]]] = {
    "boolean": CheckboxField,
    "id": IdField,
    "string": TextField,
    "phone": TextField,
    "url": TextField,
    "email": TextField,
    "textarea": TextField,
    "picklist": PicklistField,
    "multipicklist": MultiPicklistField,
    "reference": ReferenceField,
    "currency": NumberField,
    "double": NumberField,
    "percent": NumberField,
    "int": IntField,
    "date": DateField,
    "datetime": DateTimeField,
    "time": TimeField,
    "blob": BlobField,
    "base64": BlobField,
    "location": GeolocationField,
}
