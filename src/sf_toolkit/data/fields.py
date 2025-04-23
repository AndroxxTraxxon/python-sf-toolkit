import datetime
from enum import Flag, auto
import typing

T = typing.TypeVar("T")
U = typing.TypeVar("U")


class ReadOnlyAssignmentException(TypeError): ...


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
    values: list[str]

    def __init__(self, source: str):
        self.values = source.split(";")

    def __str__(self):
        return ";".join(self.values)


class FieldFlag(Flag):
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


T = typing.TypeVar("T")


class FieldConfigurableObject:
    _values: dict[str, typing.Any]
    _dirty_fields: set[str]
    _fields: typing.ClassVar[dict[str, "Field"]]

    def __init_subclass__(cls, **_) -> None:
        cls._fields = {}
        for attr_name in dir(cls):
            if attr_name.startswith("__"):
                continue
            if attr_name == "attributes":
                continue
            attr = getattr(cls, attr_name)
            if isinstance(attr, Field):
                cls._fields[attr_name] = attr

    def __init__(self):
        self._values = {}
        self._dirty_fields = set()

    @classmethod
    def keys(cls) -> frozenset[str]:
        return frozenset(cls._fields.keys())

    @classmethod
    def query_fields(cls) -> set[str]:
        fields = set()
        for field, fieldtype in cls._fields.items():
            if isinstance(fieldtype, ReferenceField) and fieldtype._py_type:
                fields.update(
                    {
                        field + "." + subfield
                        for subfield in fieldtype._py_type.query_fields()
                    }
                )
            # elif isinstance(fieldtype, ListField) and fieldtype._py_type:
            #     fields.update({field + "." + subfield for subfield in fieldtype._py_type.query_fields()})
            else:
                fields.add(field)
        return fields

    @property
    def dirty_fields(self):
        return self._dirty_fields

    @dirty_fields.deleter
    def dirty_fields(self):
        self._dirty_fields = set()

    def serialize(self, only_changes: bool = False):
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


class Field(typing.Generic[T]):
    _py_type: type[T] | None = None
    flags: set[FieldFlag]

    def __init__(self, py_type: type[T], *flags: FieldFlag):
        self._py_type = py_type
        self.flags = set(flags)

    # Add descriptor protocol methods
    def __get__(self, obj: FieldConfigurableObject, objtype=None) -> T:
        if obj is None:
            return self  # type: ignore
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

    def revive(self, value: typing.Any):
        return value

    def format(self, value: T) -> typing.Any:
        return value

    def __set_name__(self, owner, name):
        self._owner = owner
        self._name = name

    def __delete__(self, obj: FieldConfigurableObject):
        del obj._values[self._name]
        if hasattr(obj, "_dirty_fields"):
            obj._dirty_fields.discard(self._name)

    def validate(self, value):
        if value is None:
            return
        if self._py_type is not None and not isinstance(value, self._py_type):
            raise TypeError(
                f"Expected {self._py_type.__qualname__} for field {self._name} "
                f"on {self._owner.__name__}, got {type(value).__name__}"
            )

    def __str__(self):
        return str(self)


class TextField(Field[str]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(str, *flags)


class IdField(TextField):
    def validate(self, value):
        if value is None:
            return
        assert isinstance(value, str), (
            f" '{value}' is not a valid Salesforce Id. Expected a string."
        )
        assert len(value) in (15, 18), (
            f" '{value}' is not a valid Salesforce Id. Expected a string of length 15 or 18, found {len(value)}"
        )
        assert value.isalnum(), (
            f" '{value}' is not a valid Salesforce Id. Expected strictly alphanumeric characters."
        )


class PicklistField(TextField):
    _options_: list[str]

    def __init__(self, *flags: FieldFlag, options: list[str] | None = None):
        super().__init__(*flags)
        self._options_ = options or []

    def validate(self, value: str):
        if self._options_ and value not in self._options_:
            raise ValueError(
                f"Selection '{value}' is not in configured values for field {self._name}"
            )


class MultiPicklistField(Field[MultiPicklistValue]):
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
    def __init__(self, *flags: FieldFlag):
        super().__init__(float, *flags)


class IntField(Field[int]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(int, *flags)


class CheckboxField(Field[bool]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(bool, *flags)


class DateField(Field[datetime.date]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(datetime.date, *flags)

    def revive(self, value: datetime.date | str):
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(value)

    def format(self, value: datetime.date):
        return value.isoformat()


class TimeField(Field[datetime.time]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(datetime.time, *flags)

    def format(self, value):
        return value.isoformat(timespec="milliseconds")


class DateTimeField(Field[datetime.datetime]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(datetime.datetime, *flags)

    def revive(self, value: str):
        return datetime.datetime.fromisoformat(str(value))

    def format(self, value):
        if value.tzinfo is None:
            value = value.astimezone()
        return value.isoformat(timespec="milliseconds")


class ReferenceField(Field[T]):
    def revive(self, value):
        if value is None:
            return value
        assert self._py_type is not None
        if isinstance(value, self._py_type):
            return value
        if isinstance(value, dict):
            return self._py_type(**value)


class ListField(Field[list[T]]):
    _nested_type: type[T]

    def __init__(self, item_type: type[T], *flags: FieldFlag):
        self._nested_type = item_type
        super().__init__(list[item_type], *flags)

    def revive(self, value):
        if value is None:
            return value
        assert self._py_type is not None
        if isinstance(value, list):
            return [self._py_type(item) for item in value]
        if isinstance(value, dict):
            return self._py_type(**value)


FIELD_TYPE_LOOKUP: dict[str, type[Field]] = {
    "boolean": CheckboxField,
    "id": IdField,
    "string": TextField,
    "phone": TextField,
    "url": TextField,
    "email": TextField,
    "textarea": TextField,
    "picklist": TextField,
    "multipicklist": MultiPicklistField,
    "reference": ReferenceField,
    "currency": NumberField,
    "double": NumberField,
    "percent": NumberField,
    "int": NumberField,
    "date": DateField,
    "datetime": DateTimeField,
    "time": TimeField,
}
