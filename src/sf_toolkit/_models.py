from typing import TypedDict, Generic, TypeVar, NamedTuple


class SObjectAttributes(NamedTuple):
    type: str
    connection: str
    id_field: str
    blob_field: str | None
    tooling: bool


class SObjectDictAttrs(TypedDict):
    type: str
    url: str


class SObjectDict(TypedDict, total=False):
    attributes: SObjectDictAttrs


class SObjectSaveError(NamedTuple):
    statusCode: str
    message: str
    fields: list[str]

    def __str__(self):
        return f"({self.statusCode}) {self.message} ({', '.join(self.fields)})"


class SObjectSaveResult:
    id: str
    success: bool
    errors: list[SObjectSaveError]
    created: bool | None

    def __init__(
        self,
        id: str,
        success: bool,
        errors: list[SObjectSaveError | dict],
        created: bool | None = None,
    ):
        self.id = id
        self.success = success
        self.errors = [
            error if isinstance(error, SObjectSaveError) else SObjectSaveError(**error)
            for error in errors
        ]
        self.created = created

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id:{self.id} success:{self.success} errors:[{', '.join(map(str, self.errors))}]>"

    def __str__(self):
        message = f"Save Result for record {self.id} | "
        message += "SUCCESS" if self.success else "FAILURE"
        if self.errors:
            message += "\n errors:[\n  " + "\n  ".join(map(str, self.errors)) + "\n]"

        return message


SObjectRecordJSON = TypeVar("SObjectRecordJSON", bound=SObjectDict)


class QueryResultJSON(TypedDict, Generic[SObjectRecordJSON]):
    totalSize: int
    done: bool
    nextRecordsUrl: str
    records: list[SObjectRecordJSON]
