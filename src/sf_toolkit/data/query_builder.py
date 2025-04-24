from typing import Any, Literal, NamedTuple, TypeVar, Generic
from datetime import datetime, date

from ..formatting import quote_soql_value
from ..interfaces import I_SObject, I_SalesforceClient
from .._models import QueryResultJSON, SObjectRecordJSON


BooleanOperator = Literal["AND", "OR"]
Comparator = Literal["=", "!=", "<>", ">", ">=", "<", "<=", "LIKE", "INCLUDES", "IN"]


class Comparison:
    property: str
    comparator: Comparator
    value: "SoqlQuery | str | bool | datetime | date | None"

    def __init__(self, property: str, op, value):
        self.property = property
        self.operator = op
        self.value = value

    def __str__(self):
        if isinstance(self.value, SoqlQuery):
            return f"{self.property} {self.operator} ({str(self.value)})"
        return f"{self.property} {self.operator} {quote_soql_value(self.value)}"


class BooleanOperation(NamedTuple):
    operator: BooleanOperator
    conditions: list["Comparison | BooleanOperation"]

    def __str__(self):
        formatted_conditions = [
            str(condition)
            if isinstance(condition, Comparison)
            else "(" + str(condition) + ")"
            for condition in self.conditions
        ]
        return f" {self.operator} ".join(formatted_conditions)


class Negation(NamedTuple):
    condition: Comparison | BooleanOperation

    def __str__(self):
        return f"NOT ({str(self.condition)})"


class Order(NamedTuple):
    field: str
    direction: Literal["ASC", "DESC"]

    def __str__(self):
        return f"{self.field} {self.direction}"


_SObject = TypeVar("_SObject", bound=I_SObject)
_SObjectJSON = TypeVar("_SObjectJSON", bound=dict[str, Any])


class QueryResult(Generic[_SObject]):
    """
    A generic class to represent results returned by the Salesforce SOQL Query API.

    Attributes:
        done (bool):
        totalSize (int):
        records (list[T]):
        nextRecordsUrl (str, optional):
    """

    done: bool
    "Indicates whether all records have been retrieved (True) or if more batches exist (False)"
    totalSize: int
    "The total number of records that match the query criteria"
    records: list[_SObject]
    "The list of records returned by the query"
    nextRecordsUrl: str | None
    "URL to the next batch of records, if more exist"
    _connection: I_SalesforceClient
    _sobject_type: type[_SObject]
    "The SObject type this QueryResult contains records for"
    query_locator: str | None = None
    batch_size: int | None = None

    def __init__(
        self,
        connection: I_SalesforceClient,
        sobject_type: type[_SObject],
        /,
        done: bool = True,
        totalSize: int = 0,
        records: list[SObjectRecordJSON] | None = None,
        nextRecordsUrl: str | None = None,
    ):
        """
        Initialize a QueryResult object from Salesforce API response data.

        Args:
            **kwargs: Key-value pairs from the Salesforce API response.
        """
        self._connection = connection
        self._sobject_type = sobject_type
        self.done = done
        self.totalSize = totalSize
        self.records = [sobject_type(**record) for record in records] if records else []
        self.nextRecordsUrl = nextRecordsUrl
        if self.nextRecordsUrl:
            # nextRecordsUrl looks like this:
            # /services/data/v63.0/query/01gRO0000016PIAYA2-500
            self.query_locator, batch_size = self.nextRecordsUrl.rsplit(
                "/", maxsplit=1
            )[1].rsplit("-", maxsplit=1)
            self.batch_size = int(batch_size)

    def query_more(self):
        if not self.nextRecordsUrl:
            raise ValueError("Cannot get more records without nextRecordsUrl")

        result: QueryResultJSON = self._connection.get(self.nextRecordsUrl).json()
        return QueryResult(self._connection, self._sobject_type, **result)  # type: ignore


class SoqlQuery(Generic[_SObject]):
    _where: Comparison | BooleanOperation | str | None = None
    _grouping: list[str] | None = None
    _having: Comparison | BooleanOperation | str | None = None
    _limit: int | None = None
    _offset: int | None = None
    _order: list[Order | str] | None = None

    def __init__(self, sobject_type: type[_SObject]):
        self.sobject_type = sobject_type

    @property
    def fields(self):
        return list(self.sobject_type.keys())

    @property
    def sobject_name(self) -> str:
        return self.sobject_type.attributes.type

    def _sf_connection(self):
        return self.sobject_type._client_connection()

    @staticmethod
    def build_conditional(kwargs: dict[str, Any]) -> Comparison | BooleanOperation:
        raise NotImplementedError()

    def where(self, _raw: str | None = None, **kwargs):
        if _raw:
            self._where = _raw
        else:
            self._where = self.build_conditional(kwargs)
        return self

    def group_by(self, *fields: str):
        self._grouping = list(fields)
        return self

    def having(self, _raw: str | None = None, **kwargs):
        if _raw:
            self._having = _raw
        else:
            self._having = self.build_conditional(kwargs)
        return self

    def limit(self, limit: int):
        self._limit = limit
        return self

    def offset(self, offset: int):
        self._offset = offset
        return self

    def order_by(self, *orders: Order | str):
        self._order = list(orders)
        return self

    def format(self, fields: list[str] | None = None):
        if not fields:
            fields = self.fields
        segments = ["SELECT", ", ".join(fields), f"FROM {self.sobject_name}"]
        if self._where:
            segments.append(str(self._where))
        if self._grouping:
            segments.extend(["GROUP BY", ", ".join(self._grouping)])
        if self._having:
            if self._grouping is None:
                raise TypeError("Cannot use HAVING statement without GROUP BY")

        return " ".join(segments)

    def __str__(self):
        return self.format()

    def count(self) -> int:
        """
        Executes a count query instead of fetching records.
        Returns the count of records that match the query criteria.

        Returns:
            int: Number of records matching the query criteria
        """

        # Execute the query
        count_result = self.execute("COUNT()")

        # Count query returns a list with a single record containing the count
        return count_result.totalSize

    def execute(self, *_fields: str) -> QueryResult[_SObject]:
        """
        Executes the SOQL query and returns the first batch of results (up to 2000 records).
        """
        if _fields:
            fields = list(_fields)
        else:
            fields = self.fields
        client = self._sf_connection()

        result: QueryResultJSON
        if self.sobject_type.attributes.tooling:
            url = url = f"{client.data_url}/tooling/query/"
        else:
            url = f"{client.data_url}/query/"
        result = client.get(url, params={"q": self.format(fields)}).json()
        return QueryResult(client, self.sobject_type, **result)  # type: ignore
