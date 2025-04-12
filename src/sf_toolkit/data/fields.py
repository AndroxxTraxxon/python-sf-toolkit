import datetime
from enum import Flag, auto
import typing
from typing_extensions import ReadOnly, override

T = typing.TypeVar('T')
U = typing.TypeVar('U')

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


class MultiPicklistField(str):
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
    __values: dict[str, typing.Any]
    __dirty_fields: set[str]
    __fields: typing.ClassVar[dict[str, "Field"]]

    def __init_subclass__(cls, **_) -> None:
        cls.__fields = {}
        for attr_name in dir(cls):
            if attr_name.startswith("__"):
                continue
            if attr_name == "attributes":
                continue
            attr = getattr(cls, attr_name)
            if isinstance(attr, Field):
                cls.__fields[attr_name] = attr

    def __init__(self):
        setattr(self, "__values", {})
        setattr(self, "__dirty_fields", set())

    @classmethod
    def keys(cls) -> frozenset[str]:
        return frozenset(cls.__fields.keys())

    @property
    def dirty_fields(self):
        return getattr(self, "__dirty_fields")

    @dirty_fields.deleter
    def dirty_fields(self):
        setattr(self, "__dirty_fields", set())

    def serialize(self, only_changes = False):
        if only_changes:
            return {
                name: field.format(value)
                for name, value in getattr(self, "__values").items()
                if (field := self.__fields[name])
                and name in self.dirty_fields
            }

        return {
            name: field.format(value)
            for name, value in getattr(self, "__values").items()
            if (field := self.__fields[name])
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
        return getattr(obj, "__values").get(self.__name__, None)

    def __set__(self, obj: FieldConfigurableObject, value: typing.Any):
        value = self.revive(value)
        self.validate(value)
        object_values = getattr(obj, "__values")
        if FieldFlag.readonly in self.flags and self.__name__ in object_values:
            raise ReadOnlyAssignmentException(f"Field {self.__name__} is readonly")
        object_values[self.__name__] = value
        obj.dirty_fields.add(self.__name__)

    def revive(self, value: typing.Any):
        return value

    def format(self, value: T) -> typing.Any:
        return value

    def __set_name__(self, owner, name):
        self.__owner__ = owner
        self.__name__ = name

    def __delete__(self, obj: FieldConfigurableObject):
        del obj.__dict__[self.__name__]
        if hasattr(obj, "_dirty_fields"):
            obj.__dirty_fields.discard(self.__name__)

    def validate(self, value):
        if self._py_type is not None and not isinstance(value, self._py_type):
            raise TypeError(
                f"Expected {self._py_type.__qualname__} for field {self.__name__} "
                f"on {self.__owner__.__name__}, got {type(value).__name__}"
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
        assert isinstance(value, str) and len(value) in (15, 18) and value.isalnum(),\
            f" '{value}' is not a valid Salesforce Id"


class NumberField(Field[float]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(float, *flags)


class CheckboxField(Field[bool]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(bool, *flags)


class DateField(Field[datetime.date]):
    def __init__(self, *flags: FieldFlag):
        super().__init__(datetime.date, *flags)

    @override
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
        return value.isoformat(timespec='milliseconds')


class ReferenceField(Field[T]):

    def revive(self, value):
        if value is None:
            return value
        assert self._py_type is not None
        if isinstance(value, self._py_type):
            return value
        if isinstance(value, dict):
            return self._py_type(**value)
