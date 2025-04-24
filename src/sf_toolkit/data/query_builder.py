from typing import Any, Literal, NamedTuple, TypeVar, Generic
from datetime import datetime, date

from ..formatting import quote_soql_value
from ..interfaces import I_SObject, I_SalesforceClient
from .._models import QueryResultJSON, SObjectRecordJSON


BooleanOperator = Literal["AND", "OR", "NOT"]
Comparator = Literal["=", "!=", "<>", ">", ">=", "<", "<=", "LIKE", "INCLUDES", "IN"]
AGGREGATE_FUNCTIONS = ["AVG", "COUNT", "COUNT_DISTINCT", "MIN", "MAX", "SUM"]


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


def EQ(property: str, value):
    return Comparison(property, "=", value)

def NE(property: str, value):
    return Comparison(property, "!=", value)

def GT(property: str, value):
    return Comparison(property, ">", value)

def GE(property: str, value):
    return Comparison(property, ">=", value)

def LT(property: str, value):
    return Comparison(property, "<", value)

def LE(property: str, value):
    return Comparison(property, "<=", value)

def LIKE(property: str, value):
    return Comparison(property, "LIKE", value)

def INCLUDES(property: str, value):
    return Comparison(property, "INCLUDES", value)

def IN(property: str, value):
    return Comparison(property, "IN", value)

def NOT_IN(property: str, value):
    return Comparison(property, "NOT IN", value)


class BooleanOperation:
    operator: BooleanOperator
    conditions: list["Comparison | BooleanOperation | str"]

    def __init__(self, operator: BooleanOperator, conditions: list["Comparison | BooleanOperation | str"]):
        self.operator = operator
        self.conditions = conditions

    def __str__(self):
        formatted_conditions = [
            str(condition)
            if isinstance(condition, Comparison)
            else "(" + str(condition) + ")"
            for condition in self.conditions
        ]
        return f" {self.operator} ".join(formatted_conditions)

def OR(*conditions: "Comparison | BooleanOperation | str"):
    return BooleanOperation("OR", list(conditions))

def AND(*conditions: "Comparison | BooleanOperation | str"):
    return BooleanOperation("AND", list(conditions))


class NOT(BooleanOperation):
    def __init__(self, condition: "Comparison | BooleanOperation | str"):
        super().__init__("NOT", [condition])

    def __str__(self):
        return f"NOT ({str(self.conditions[0])})"


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
        if "SObjectList" not in globals():
            global SObjectList
            from .sobject import SObjectList
        self.records = SObjectList([
            sobject_type(**record) for record in records   # type: ignore
        ] if records else [])
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

    @classmethod
    def build_conditional(cls, arg: str, value)-> Comparison | NOT:
        op = "="
        negated = arg.startswith("NOT__")
        if negated:
            arg = arg.removeprefix("NOT__")
        if arg.endswith("__ne"):
            arg = arg.removesuffix("__ne")
            op = "!="
        elif arg.endswith("__gt"):
            arg = arg.removesuffix("__gt")
            op = ">"
        elif arg.endswith("__lt"):
            arg = arg.removesuffix("__lt")
            op = "<"
        elif arg.endswith("__ge"):
            arg = arg.removesuffix("__ge")
            op = ">="
        elif arg.endswith("__le"):
            arg = arg.removesuffix("__le")
            op = "<="
        elif arg.endswith("__in"):
            arg = arg.removesuffix("__in")
            op = "IN"
        elif arg.endswith("__like"):
            arg = arg.removesuffix("__like")
            op = "LIKE"
        elif arg.endswith("__includes"):
            arg = arg.removesuffix("__includes")
            op = "INCLUDES"

        if any(arg.startswith(f"{func}__") for func in AGGREGATE_FUNCTIONS):
            func, arg = arg.split("__", maxsplit=1)
            arg = f"{func}({arg})"

        if negated:
            return NOT(Comparison(arg, op, value))
        else:
            return Comparison(arg, op, value)

    @classmethod
    def build_conditional_clause(
        cls,
        kwargs: dict[str, Any],
        mode: Literal["any", "all"] = "all",
    ) -> Comparison | BooleanOperation:
        assert len(kwargs) > 0
        if len(kwargs) == 1:
            arg, value = next(iter(kwargs.items()))
            return cls.build_conditional(arg, value)
        conditions = (
            cls.build_conditional(arg, value)
            for arg, value in kwargs.items()
        )
        if mode == "any":
            return OR(*conditions)
        elif mode == "all":
            return AND(*conditions)
        else:
            raise ValueError(f"Invalid mode: {mode}")

    def where(
        self,
        _raw: Comparison | BooleanOperation | str | None = None,
        _mode: Literal["any", "all"] = "all", **kwargs
    ):
        if _raw:
            self._where = _raw
        else:
            self._where = self.build_conditional_clause(kwargs, _mode)
        return self

    def and_where(
        self,
        _raw: Comparison | BooleanOperation | str | None = None,
        _mode: Literal["any", "all"] = "all",
        **kwargs: Any
    ):
        assert self._where is not None, "where() must be called before and_where()"
        if _raw:
            self._where = AND(self._where, _raw)
        else:
            self._where = AND(self._where, self.build_conditional_clause(kwargs, _mode))
        return self

    def or_where(
        self,
        _raw: Comparison | BooleanOperation | str | None = None,
        _mode: Literal["any", "all"] = "all",
        **kwargs: Any
    ):
        assert self._where is not None, "where() must be called before or_where()"
        if _raw:
            self._where = OR(self._where, _raw)
        else:
            self._where = OR(self._where, self.build_conditional_clause(kwargs, _mode))
        return self

    def group_by(self, *fields: str):
        self._grouping = list(fields)
        return self

    def having(
        self,
        _raw: Comparison | BooleanOperation | str | None = None,
        _mode: Literal["any", "all"] = "all",
        **kwargs
    ):
        if _raw:
            self._having = _raw
        else:
            self._having = self.build_conditional_clause(kwargs, _mode)
        return self

    def and_having(
        self,
        _raw: Comparison | BooleanOperation | str | None = None,
        _mode: Literal["any", "all"] = "all",
        **kwargs: Any
    ):
        assert self._having is not None, "having() must be called before and_having()"
        if _raw:
            self._having = AND(self._having, _raw)
        else:
            self._having = AND(self._having, self.build_conditional_clause(kwargs, _mode))
        return self

    def or_having(
        self,
        _raw: Comparison | BooleanOperation | str | None = None,
        _mode: Literal["any", "all"] = "all",
        **kwargs: Any
    ):
        assert self._having is not None, "having() must be called before or_having()"
        if _raw:
            self._having = OR(self._having, _raw)
        else:
            self._having = OR(self._having, self.build_conditional_clause(kwargs, _mode))
        return self

    def limit(self, limit: int):
        self._limit = limit
        return self

    def offset(self, offset: int):
        self._offset = offset
        return self

    def order_by(self, *orders: Order, **kw_orders: Literal["ASC", "DESC"]):
        self._order = list(orders)
        self._order.extend(
            Order(field, direction) for field, direction in kw_orders.items()
        )
        return self

    def format(self, fields: list[str] | None = None):
        if not fields:
            fields = self.fields
        segments = ["SELECT", ", ".join(fields), f"FROM {self.sobject_name}"]
        if self._where:
            segments.extend(["WHERE", str(self._where)])
        if self._grouping:
            segments.extend(["GROUP BY", ", ".join(self._grouping)])
        if self._having:
            if self._grouping is None:
                raise TypeError("Cannot use HAVING statement without GROUP BY")
            segments.extend(["HAVING", str(self._having)])
        if self._order:
            segments.extend(["ORDER BY", ", ".join(map(str, self._order))])
        if self._limit:
            segments.append(f"LIMIT {self._limit}")
        if self._offset:
            segments.append(f"OFFSET {self._offset}")

        query = " ".join(segments).replace("\r", " ").replace("\n", " ")
        while "  " in query:
            query = query.replace("  ", " ")
        return query

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
            url = f"{client.data_url}/tooling/query/"
        else:
            url = f"{client.data_url}/query/"
        result = client.get(url, params={"q": self.format(fields)}).json()
        return QueryResult(client, self.sobject_type, **result)  # type: ignore
