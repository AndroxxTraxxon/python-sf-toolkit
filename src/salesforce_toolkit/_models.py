from typing import NamedTuple, TypedDict


class SObjectAttributes(NamedTuple):
    type: str
    connection: str


class SObjectDictAttrs(TypedDict):
    type: str
    url: str


class SObjectDict(TypedDict, total=False):
    attributes: SObjectDictAttrs
