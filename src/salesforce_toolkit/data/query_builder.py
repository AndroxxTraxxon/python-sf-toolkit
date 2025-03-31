from functools import cached_property
from typing import Literal, NamedTuple, TypeVar, Generic
from datetime import datetime, date
from ..protocols import SObjectProtocol, SalesforceClientProtocol
from ..formatting import quote_soql_value

from ..client import SalesforceClient

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


T = TypeVar('T', bound=SObjectProtocol)

class QueryResult(Generic[T]):
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
    records: list[T]
    nextRecordsUrl: str | None

    def __init__(self,
        sobject_type: type[T],
        done: bool = True,
        totalSize: int = 0,
        records: list[T] | None = None,
        nextRecordsUrl: str | None = None
    ):
        """
        Initialize a QueryResult object from Salesforce API response data.

        Args:
            **kwargs: Key-value pairs from the Salesforce API response.
        """
        self.done = done
        self.totalSize = totalSize
        self.records = [sobject_type(**record) for record in records] if records else []
        self.nextRecordsUrl = nextRecordsUrl



class SoqlSelect(Generic[T]):
    where: Comparison | BooleanOperator | None = None
    grouping: list[str] | None = None
    having: Comparison | BooleanOperator | None = None
    limit: int | None = None
    offset: int | None = None
    order: list[Order] | None = None

    def __init__(self, sobject_type: type[SObjectProtocol]):
        self.sobject_type = sobject_type

    @property
    def sf_connection(self) -> SalesforceClientProtocol:
        return self.sobject_type._client_connection

    @property
    def fields(self):
        return list(self.sobject_type.fields)

    @property
    def sobject(self):
        return self.sobject_type._sf_attrs.type


    def _sf_connection(self):
        return self.sobject_type._client_connection


    def format(self, fields: list[str]):
        segments = ["SELECT", ", ".join(fields), f"FROM {self.sobject}"]
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
        count_result = self.execute(["COUNT()"])

        # Count query returns a list with a single record containing the count
        if count_result and len(count_result) > 0:
            return int(count_result[0]["expr0"])
        return 0

    def execute(self, fields: list[str] | None) -> list[dict]:
        """
        Executes the SOQL query and returns the first batch of results (up to 2000 records).

        Returns:
            list[dict]: List of records matching the query criteria
        """
        if not fields:
            fields = self.fields
        connection = self._sf_connection()
        query_string = self.format(fields)

        result = connection.get(f"{connection.data_url}/query?q={query_string}").json()
        query_result = QueryResult(**result, )

        return query_result

    def
