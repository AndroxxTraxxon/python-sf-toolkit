from typing import TypedDict, Generic, TypeVar, Any


SObjectRecordJSON = TypeVar("SObjectRecordJSON", bound=dict[str, Any])

class QueryResultJSON(TypedDict, Generic[SObjectRecordJSON]):
    totalSize: int
    done: bool
    nextRecordsUrl: str
    records: list[SObjectRecordJSON]
