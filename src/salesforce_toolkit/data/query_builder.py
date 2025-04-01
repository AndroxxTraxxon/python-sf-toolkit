from typing import Any, Literal, NamedTuple, TypeVar, Generic
from datetime import datetime, date

from salesforce_toolkit.data.apimodels import QueryResultJSON
from salesforce_toolkit.interfaces import I_SObject
from ..formatting import quote_soql_value


BooleanOperator = Literal["AND", "OR"]
Comparator = Literal["=", "!=", "<>", ">", ">=", "<", "<=", "LIKE", "INCLUDES"]

class Comparison:
    property: str
    comparator: Comparator
    value: str | bool | datetime | date | None

    def __init__(self, property: str, op, value):
        self.property = property
        self.operator = op
        self.value = value

    def __str__(self):
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

_SObject = TypeVar('_SObject', bound=I_SObject)
_SObjectJSON = TypeVar('_SObjectJSON', bound=dict[str, Any])
class QueryResult(Generic[_SObject]):
    """
    A generic class to represent results returned by the Salesforce SOQL Query API.

    Attributes:
        done (bool): Indicates whether all records have been retrieved (True) or if more batches exist (False)
        totalSize (int): The total number of records that match the query criteria
        records (list[T]): The list of records returned by the query
        nextRecordsUrl (str, optional): URL to the next batch of records, if more exist
    """
    done: bool
    totalSize: int
    records: list[_SObject]
    nextRecordsUrl: str | None
    _sobject_type: type[_SObject]

    def __init__(self,
        sobject_type: type[_SObject], / ,
        done: bool = True,
        totalSize: int = 0,
        records: list[dict[str, Any]] | None = None,
        nextRecordsUrl: str | None = None
    ):
        """
        Initialize a QueryResult object from Salesforce API response data.

        Args:
            **kwargs: Key-value pairs from the Salesforce API response.
        """
        self._sobject_type = sobject_type
        self.done = done
        self.totalSize = totalSize
        self.records = [sobject_type(**record) for record in records] if records else []
        self.nextRecordsUrl = nextRecordsUrl
        if self.nextRecordsUrl:
            self.query_locator, self.batch_size = self.nextRecordsUrl.rsplit("/", maxsplit=1)[1].rsplit("-", maxsplit=1)

    def query_more(self):
        if not self.nextRecordsUrl:
            raise ValueError("Cannot get more records without nextRecordsUrl")

        client = self._sobject_type._client_connection()
        result: QueryResultJSON = client.get(self.nextRecordsUrl).json()
        return QueryResult(self._sobject_type, **result)


class SoqlSelect(Generic[_SObject]):
    where: Comparison | BooleanOperator | None = None
    grouping: list[str] | None = None
    having: Comparison | BooleanOperator | None = None
    limit: int | None = None
    offset: int | None = None
    order: list[Order] | None = None

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


    def format(self, fields: list[str]):
        segments = ["SELECT", ", ".join(fields), f"FROM {self.sobject_name}"]
        if self.where:
            segments.append(str(self.where))
        if self.grouping:
            segments.extend(["GROUP BY", ", ".join(self.grouping)])
        if self.having:
            if self.grouping is None:
                raise TypeError("Cannot use HAVING statement without GROUP BY")

        return " ".join(segments)

    def count(self) -> int:
        """
        Executes a count query instead of fetching records.
        Returns the count of records that match the query criteria.

        Returns:
            int: Number of records matching the query criteria
        """

        # Execute the query
        count_result = self.query(["COUNT()"])

        # Count query returns a list with a single record containing the count
        return count_result.totalSize

    def query(self, fields: list[str] | None = None) -> QueryResult[_SObject]:
        """
        Executes the SOQL query and returns the first batch of results (up to 2000 records).
        """
        if not fields:
            fields = self.fields
        client = self._sf_connection()

        result: QueryResultJSON = client.get(
            f"{client.data_url}/query",
            params={"q": self.format(fields)}
        ).json()
        return QueryResult(self.sobject_type, **result)
