"""
Module for basic field and field-configurable object scaffolding
"""

from collections import defaultdict
import datetime
from enum import Flag, auto
import typing
import io
from pathlib import Path
import warnings

from httpx._types import FileContent  # type: ignore

T = typing.TypeVar("T")
U = typing.TypeVar("U")


class ReadOnlyAssignmentException(TypeError):
    """Exception for when value assignments are performed on readonly fields"""


class SObjectFieldDescribe(typing.NamedTuple):
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
    defaultValue: typing.Any = None
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


class MultiPicklistValue(str):
    """type for semicolon-delimited multi-value attributes"""

    values: list[str]

    def __init__(self, source: str):
        self.values = source.split(";")

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

    _values: dict[str, typing.Any]
    _dirty_fields: set[str]
    _fields: typing.ClassVar[dict[str, "Field"]]
    _type_field_registry: typing.ClassVar[
        dict[type["FieldConfigurableObject"], dict[str, "Field"]]
    ] = defaultdict(dict)

    def __init__(self, _strict_fields: bool = False, **field_values):
        self._values = {}
        self._dirty_fields = set()
        for field, value in field_values.items():
            if field not in self._fields:
                message = f"Field {field} not defined for {type(self).__qualname__}"
                if _strict_fields:
                    raise KeyError(message)
                else:
                    warnings.warn(message)
            setattr(self, field, value)
        self._dirty_fields.clear()

    def __init_subclass__(cls) -> None:
        cls._fields = cls._type_field_registry[cls]
        for parent in cls.__mro__:
            if parent_fields := getattr(parent, "_fields", None):
                for field, fieldtype in parent_fields.items():
                    if field not in cls._fields:
                        cls._fields[field] = fieldtype

    @classmethod
    def keys(cls) -> typing.Iterable[str]:
        """
        Returns the field names for the fields configured on the class
        This is most frequently used with the **operator
        """
        assert hasattr(cls, "_fields"), (
            f"No Field definitions found for class {cls.__name__}"
        )
        return cls._fields.keys()

    @classmethod
    def query_fields(cls) -> list[str]:
        """
        returns the list of fully qualified fields as they would
        need to appear in a SOQL query
        """
        assert hasattr(cls, "_fields"), (
            f"No Field definitions found for class {cls.__name__}"
        )
        fields = list()
        for field, fieldtype in cls._fields.items():
            if isinstance(fieldtype, ReferenceField) and isinstance(
                fieldtype.meta_py_type, FieldConfigurableObject
            ):
                fields.extend(
                    [
                        field + "." + subfield
                        for subfield in fieldtype.meta_py_type.query_fields()
                    ]
                )
            else:
                fields.append(field)
        return fields

    @property
    def dirty_fields(self) -> set[str]:
        """
        Returns the set of fields that have been modified since the last
        time this object was `.save()`-d to Salesforce
        """
        return self._dirty_fields

    @dirty_fields.deleter
    def dirty_fields(self):
        self._dirty_fields = set()

    def serialize(self, only_changes: bool = False, all_fields: bool = False):
        """
        Serialize this record to standard python types (dict, list, str, etc.)
        for easier transport
        with file formats like JSON, YAML
        """
        assert not (only_changes and all_fields), (
            "Cannot serialize both only changes and all fields."
        )
        if all_fields:
            return {
                name: field.format(self._values.get(name, None))
                for name, field in self._fields.items()
            }

        if only_changes:
            return {
                name: field.format(value)
                for name, value in self._values.items()
                if (field := self._fields[name])
                and name in self.dirty_fields
                and FieldFlag.readonly not in field.flags
            }

        return {
            name: field.format(value)
            for name, value in self._values.items()
            if (field := self._fields[name]) and FieldFlag.readonly not in field.flags
        }

    def __getitem__(self, name):
        if name not in self.keys():
            raise KeyError(f"Undefined field {name} on object {type(self)}")
        return getattr(self, name, None)

    def __setitem__(self, name, value):
        if name not in self.keys():
            raise KeyError(f"Undefined field {name} on object {type(self)}")
        setattr(self, name, value)


_FCO_Type = typing.TypeVar("_FCO_Type", bound=FieldConfigurableObject)


class Field(typing.Generic[T]):
    """
    Base class for all configurable field types
    """

    _owner: type
    _py_type: type[T] | None = None
    flags: set[FieldFlag]

    def __init__(self, py_type: type[T], *flags: FieldFlag):
        self._py_type = py_type
        self.flags = set(flags)
        self._owner = type(None)
        self._name = ""

    # Add descriptor protocol methods
    def __get__(self, obj: FieldConfigurableObject, objtype=None) -> T:
        if obj is None:
            return self
        return obj._values.get(self._name)  # type: ignore

    def __set__(self, obj: FieldConfigurableObject, value: typing.Any):
        value = self.revive(value)
        self.validate(value)
        if FieldFlag.readonly in self.flags and self._name in obj._values:
            raise ReadOnlyAssignmentException(
                f"Field {self._name} is readonly on object {self._owner.__name__}"
            )
        obj._values[self._name] = value
        obj.dirty_fields.add(self._name)

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
        cls._type_field_registry[cls][name] = self

    def __delete__(self, obj: FieldConfigurableObject):
        del obj._values[self._name]
        if hasattr(obj, "_dirty_fields"):
            obj._dirty_fields.discard(self._name)

    def validate(self, value):
        """Validates the revived value passed to the field"""
        if value is None:
            return
        if self._py_type is not None and not isinstance(value, self._py_type):
            raise TypeError(
                f"Expected {self._py_type.__qualname__} for field {self._name} "
                f"on {self._owner.__name__}, got {type(value).__name__}"
            )


class RawField(Field[typing.Any]):
    """
    A Field that does no transformation or validation on the values passed to it.
    """

    def __init__(self, *flags: FieldFlag):
        super().__init__(type(None), *flags)

    def validate(self, value):
        return


class TextField(Field[str]):
    """
    A field to contain text or string values
    """

    def __init__(self, *flags: FieldFlag):
        super().__init__(str, *flags)


class IdField(TextField):
    """
    A field to contain 15- or 18-character alphanumeric Id
    Strings used by Salesforce
    """

    def validate(self, value):
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

    def __init__(self, *flags: FieldFlag, options: list[str] | None = None):
        super().__init__(*flags)
        self._options_ = options or []

    def validate(self, value: str):
        if self._options_ and value not in self._options_:
            raise ValueError(
                f"Selection '{value}' is not in "
                f"configured values for field {self._name}"
            )


class MultiPicklistField(Field[MultiPicklistValue]):
    """
    A field to contain text values (optionally more than one)
    chosen from a pre-configured list
    """

    _options_: list[str]

    def __init__(self, *flags: FieldFlag, options: list[str] | None = None):
        super().__init__(MultiPicklistValue, *flags)
        self._options_ = options or []

    def revive(self, value: str):
        return MultiPicklistValue(value)

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

    def __init__(self, *flags: FieldFlag):
        super().__init__(float, *flags)

    def revive(self, value: typing.Any):
        return None if value is None else float(value)


class IntField(Field[int]):
    """
    A field to contain an integer numeric value.
    """

    def __init__(self, *flags: FieldFlag):
        super().__init__(int, *flags)

    def revive(self, value: typing.Any):
        return None if value is None else int(value)


class CheckboxField(Field[bool]):
    """
    A field to contain a boolean value.
    """

    def __init__(self, *flags: FieldFlag):
        super().__init__(bool, *flags)

    def revive(self, value: typing.Any):
        return None if value is None else bool(value)


class DateField(Field[datetime.date]):
    """
    A field to contain a date value.
    """

    def __init__(self, *flags: FieldFlag):
        super().__init__(datetime.date, *flags)

    def revive(self, value: datetime.date | str):
        if value is None:
            return None
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(value)

    def format(self, value: datetime.date):
        return value.isoformat()


class TimeField(Field[datetime.time]):
    """
    A field to contain a time value.
    """

    def __init__(self, *flags: FieldFlag):
        super().__init__(datetime.time, *flags)

    def format(self, value):
        if value is None:
            return None
        return value.isoformat(timespec="milliseconds")

    def revive(self, value):
        return datetime.time.fromisoformat(str(value))


class DateTimeField(Field[datetime.datetime]):
    """
    A field to contain a datetime value.
    """

    def __init__(self, *flags: FieldFlag):
        super().__init__(datetime.datetime, *flags)

    def revive(self, value: str | None):
        if value is None:
            return None
        return datetime.datetime.fromisoformat(str(value))

    def format(self, value: datetime.datetime) -> str:
        if value.tzinfo is None:
            value = value.astimezone()
        return value.isoformat(timespec="milliseconds")


class ReferenceField(Field[_FCO_Type]):
    """
    A field to contain a nested field configurable object,
    typically represented in Salesforce as a lookup or master-detail relationship
    """

    def revive(self, value):
        if value is None:
            return None
        assert self._py_type is not None
        if isinstance(value, self._py_type):
            return value
        if isinstance(value, dict):
            return self._py_type(**value)

    def format(self, value: _FCO_Type):
        try:
            return value.serialize()
        except AttributeError:
            return value


class ListField(Field[list[_FCO_Type]]):
    """
    A field to contain a nested list of field configurable object,
    typically represented in Salesforce as a lookup or master-detail relationship
    """

    _nested_type: type[_FCO_Type]

    def __init__(self, item_type: type[_FCO_Type], *flags: FieldFlag):
        self._nested_type = item_type
        super().__init__(list, *flags)

        try:
            global SObjectList
            # ensure SObjectList is imported
            # at the time of SObject type/class definition
            SObjectList  # type: ignore
        except NameError:
            from .sobject import SObjectList

    def revive(self, value: list[dict | _FCO_Type] | None):  # type: ignore
        if value is None:
            return None
        if isinstance(value, SObjectList):
            return value
        if isinstance(value, list):
            if issubclass(self._nested_type, FieldConfigurableObject):
                return SObjectList([self._nested_type(**item) for item in value])  # type: ignore
            return value
        if isinstance(value, dict):
            # assume the dict is a QueryResult-formatted dictionary
            if issubclass(self._nested_type, FieldConfigurableObject):
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
        elif isinstance(self.data, io.IOBase):
            # Reset the file pointer if it's a file object
            if hasattr(self.data, "seek"):
                self.data.seek(0)
            return self.data.read()
        else:
            raise TypeError(f"Unsupported data type: {type(self.data)}")

    def __exit__(self, exc_type, exc_value, traceback):
        if self._filepointer:
            self._filepointer.close()


class BlobField(Field[BlobData]):
    """Field type for handling blob data in Salesforce"""

    def __init__(self, *flags: FieldFlag):
        super().__init__(BlobData, *flags)

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
        obj.dirty_fields.add(self._name)


FIELD_TYPE_LOOKUP: dict[str, type[Field]] = {
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
}
