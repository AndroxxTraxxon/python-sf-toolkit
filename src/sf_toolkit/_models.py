from typing import TypedDict, Generic, TypeVar, NamedTuple


class SObjectAttributes(NamedTuple):
    type: str
    connection: str


class SObjectDictAttrs(TypedDict):
    type: str
    url: str


class SObjectDict(TypedDict, total=False):
    attributes: SObjectDictAttrs


SObjectRecordJSON = TypeVar("SObjectRecordJSON", bound=SObjectDict)

class QueryResultJSON(TypedDict, Generic[SObjectRecordJSON]):
    totalSize: int
    done: bool
    nextRecordsUrl: str
    records: list[SObjectRecordJSON]
