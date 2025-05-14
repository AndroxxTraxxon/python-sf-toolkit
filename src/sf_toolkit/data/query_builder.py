from asyncio import Task, create_task
from typing import Any, AsyncIterator, Iterator, Literal, NamedTuple, TypeVar, Generic
from datetime import datetime, date

from ..client import SalesforceClient
from .fields import ListField
from .sobject import SObject, SObjectList

from ..formatting import quote_soql_value
from .._models import QueryResultJSON, SObjectRecordJSON


BooleanOperator = Literal["AND", "OR", "NOT"]
Comparator = Literal["=", "!=", "<>", ">", ">=", "<", "<=", "LIKE", "INCLUDES", "IN"]
AGGREGATE_FUNCTIONS = ["AVG", "COUNT", "COUNT_DISTINCT", "MIN", "MAX", "SUM"]


class Comparison:
    prop: str
    comparator: Comparator
    value: "SoqlQuery | str | bool | datetime | date | None"

    def __init__(self, prop: str, op, value):
        self.prop = prop
        self.operator = op
        self.value = value

    def __str__(self):
        if isinstance(self.value, SoqlQuery):
            return f"{self.prop} {self.operator} ({str(self.value)})"
        elif self.operator == "IN" and isinstance(self.value, str):
            return f"{self.prop} {self.operator} ({self.value})"
        return f"{self.prop} {self.operator} {quote_soql_value(self.value)}"


def EQ(prop: str, value):
    return Comparison(prop, "=", value)


def NE(prop: str, value):
    return Comparison(prop, "!=", value)


def GT(prop: str, value):
    return Comparison(prop, ">", value)


def GE(prop: str, value):
    return Comparison(prop, ">=", value)


def LT(prop: str, value):
    return Comparison(prop, "<", value)


def LE(prop: str, value):
    return Comparison(prop, "<=", value)


def LIKE(prop: str, value):
    return Comparison(prop, "LIKE", value)


def INCLUDES(prop: str, value):
    return Comparison(prop, "INCLUDES", value)


def IN(prop: str, value):
    return Comparison(prop, "IN", value)


def NOT_IN(prop: str, value):
    return Comparison(prop, "NOT IN", value)


class BooleanOperation:
    operator: BooleanOperator
    conditions: list["Comparison | BooleanOperation | str"]

    def __init__(
        self,
        operator: BooleanOperator,
        conditions: list["Comparison | BooleanOperation | str"],
    ):
        self.operator = operator
        self.conditions = conditions

    def __str__(self):
        formatted_conditions = [
            (
                str(condition)
                if isinstance(condition, Comparison)
                else "(" + str(condition) + ")"
            )
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


_SObject = TypeVar("_SObject", bound=SObject)
_SObjectJSON = TypeVar("_SObjectJSON", bound=dict[str, Any])


class QueryResultBatch(Generic[_SObject]):
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
    _connection: SalesforceClient
    _sobject_type: type[_SObject]
    "The SObject type this QueryResult contains records for"
    query_locator: str | None = None
    batch_size: int | None = None

    def __init__(
        self,
        sobject_type: type[_SObject],
        /,
        done: bool = True,
        totalSize: int = 0,
        records: list[SObjectRecordJSON] | None = None,
        nextRecordsUrl: str | None = None,
        connection: SalesforceClient | None = None,
    ):
        """
        Initialize a QueryResult object from Salesforce API response data.

        Args:
            **kwargs: Key-value pairs from the Salesforce API response.
        """
        self._connection = connection or SalesforceClient.get_connection(
            sobject_type.attributes.connection
        )  # type: ignore
        self._sobject_type = sobject_type
        self.done = done
        self.totalSize = totalSize
        self.records = SObjectList(
            [sobject_type(**record) for record in records]  # type: ignore
            if records
            else []
        )
        self.nextRecordsUrl = nextRecordsUrl
        if self.nextRecordsUrl:
            # nextRecordsUrl looks like this:
            # /services/data/v63.0/query/01gRO0000016PIAYA2-500
            self.query_locator, batch_size = self.nextRecordsUrl.rsplit(
                "/", maxsplit=1
            )[1].rsplit("-", maxsplit=1)
            self.batch_size = int(batch_size)

    def query_more(self) -> "QueryResultBatch[_SObject]":
        if not self.nextRecordsUrl:
            raise ValueError("Cannot get more records without nextRecordsUrl")

        result: QueryResultJSON = self._connection.get(self.nextRecordsUrl).json()
        return QueryResultBatch(
            self._sobject_type,
            connection=self._connection,
            **result,  # type: ignore
        )

    async def query_more_async(self) -> "QueryResultBatch[_SObject]":
        if not self.nextRecordsUrl:
            raise ValueError("Cannot get more records without nextRecordsUrl")

        result: QueryResultJSON = (
            await self._connection.as_async.get(self.nextRecordsUrl)
        ).json()
        return QueryResultBatch(
            self._sobject_type,
            connection=self._connection,
            **result,  # type: ignore
        )


class QueryResult(Generic[_SObject]):
    batches: list[QueryResultBatch[_SObject]]
    total_size: int
    batch_index: int = 0
    record_index: int = 0
    _async_tasks: list[Task] | None

    def __init__(
        self,
        batches: list[QueryResultBatch[_SObject]],
        _async_tasks: list[Task] | None = None,
    ):
        self.batches = batches
        self.total_size = batches[0].totalSize
        self._async_tasks = _async_tasks

    def __len__(self):
        return self.total_size

    @property
    def done(self):
        return self.batches[self.batch_index].done

    def as_list(self) -> SObjectList[_SObject]:
        return SObjectList(
            self, connection=self.batches[0]._sobject_type.attributes.connection
        )

    async def as_list_async(self):
        return await SObjectList.async_init(
            self, self.batches[0]._sobject_type.attributes.connection
        )

    async def _fetch_query_locator_batch(self, query_locator_url: str):
        connection = self.batches[0]._connection.as_async
        result: QueryResultJSON = (await connection.get(query_locator_url)).json()
        return QueryResultBatch(
            self.batches[0]._sobject_type,
            connection=self.batches[0]._connection,
            **result,  ## type: ignore
        )

    def copy(self) -> "QueryResult[_SObject]":
        """Perform a shallow copy of the QueryResult object."""
        return QueryResult(self.batches, self._async_tasks)

    def __iter__(self) -> Iterator[_SObject]:
        return self.copy()

    def schedule_async_tasks(self):
        assert self.batches[0].nextRecordsUrl is not None, (
            "Cannot iterate with no query locator"
        )
        url_root, _ = self.batches[0].nextRecordsUrl.rsplit("-", maxsplit=1)
        batch_size = len(self.batches[0].records)
        fetched_record_count = batch_size * self.batch_index
        self._async_tasks = [
            create_task(self._fetch_query_locator_batch(f"{url_root}-{index}"))
            for index in range(fetched_record_count, len(self), batch_size)
        ]

    def __aiter__(self) -> AsyncIterator[_SObject]:
        if not self.done:
            self.schedule_async_tasks()

        return self.copy()

    def __next__(self) -> _SObject:
        try:
            return self.batches[self.batch_index].records[self.record_index]
        except IndexError:
            if self.done:
                raise StopIteration
            if self.batch_index >= (len(self.batches) - 1):
                self.batches.append(self.batches[self.batch_index].query_more())
            self.batch_index += 1
            self.record_index = 0
            return self.batches[self.batch_index].records[self.record_index]
        finally:
            self.record_index += 1

    async def __anext__(self) -> _SObject:
        try:
            return self.batches[self.batch_index].records[self.record_index]
        except IndexError:
            if self.done:
                raise StopAsyncIteration
            if self._async_tasks:
                self.batches.append(await self._async_tasks.pop(0))
                if not self._async_tasks:
                    self._async_tasks = None
            elif self.batch_index >= (len(self.batches) - 1):
                self.batches.append(await self.batches[-1].query_more_async())
            self.batch_index += 1
            self.record_index = 0
            return self.batches[self.batch_index].records[self.record_index]
        finally:
            self.record_index += 1


class SoqlQuery(Generic[_SObject]):
    sobject_type: type[_SObject]
    _object_relationship_name: str | None = None
    _where: Comparison | BooleanOperation | str | None = None
    _grouping: list[str] | None = None
    _having: Comparison | BooleanOperation | str | None = None
    _limit: int | None = None
    _offset: int | None = None
    _order: list[Order | str] | None = None
    _subqueries: dict[str, "SoqlQuery"]
    _include_deleted: bool

    def __init__(self, sobject_type: type[_SObject], include_deleted: bool = False):
        self.sobject_type = sobject_type
        self._subqueries = {}
        self._include_deleted = include_deleted

    @property
    def fields(self):
        fields = []
        for field in self.sobject_type.query_fields():
            if isinstance(field_def := self.sobject_type._fields.get(field), ListField):
                subquery = self._subqueries.get(field)
                if not subquery:
                    subquery = field_def._nested_type.query()
                    subquery._object_relationship_name = field
                fields.append(f"({str(subquery)})")
            else:
                fields.append(field)
        return fields

    def filter_subqueries(self, **subqueries: "SoqlQuery"):
        """
        Configure Parent-To-Child Relationship queries

        By default, all records are returned in the subquery (no filtering).

        https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/sforce_api_calls_soql_relationships_query_using.htm

        Args:
            **subqueries: A dictionary of field names and SoqlQuery objects.

        Returns:
            self: The current SoqlQuery object.
        """
        for field, subquery in subqueries.items():
            assert isinstance(self.sobject_type._fields.get(field), ListField), (
                f"Field '{field}' is not a ListField"
            )
            subquery._object_relationship_name = field
            self._subqueries[field] = subquery
        return self

    @property
    def sobject_name(self) -> str:
        return self.sobject_type.attributes.type

    def _sf_connection(self):
        return self.sobject_type._client_connection()

    @classmethod
    def build_conditional(cls, arg: str, value) -> Comparison | NOT:
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
            cls.build_conditional(arg, value) for arg, value in kwargs.items()
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
        _mode: Literal["any", "all"] = "all",
        **kwargs,
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
        **kwargs: Any,
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
        **kwargs: Any,
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
        **kwargs,
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
        **kwargs: Any,
    ):
        assert self._having is not None, "having() must be called before and_having()"
        if _raw:
            self._having = AND(self._having, _raw)
        else:
            self._having = AND(
                self._having, self.build_conditional_clause(kwargs, _mode)
            )
        return self

    def or_having(
        self,
        _raw: Comparison | BooleanOperation | str | None = None,
        _mode: Literal["any", "all"] = "all",
        **kwargs: Any,
    ):
        assert self._having is not None, "having() must be called before or_having()"
        if _raw:
            self._having = OR(self._having, _raw)
        else:
            self._having = OR(
                self._having, self.build_conditional_clause(kwargs, _mode)
            )
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
        assert fields, "Fields cannot be empty"
        segments = [
            "SELECT",
            ", ".join(fields),
            f"FROM {self._object_relationship_name or self.sobject_name}",
        ]
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

    def count(self, connection: SalesforceClient | str | None = None) -> int:
        """
        Executes a count query instead of fetching records.
        Returns the count of records that match the query criteria.

        Returns:
            int: Number of records matching the query criteria
        """

        # Execute the query
        count_result = self.execute("COUNT()", connection=connection)

        # Count query returns a list with a single record containing the count
        return len(count_result)

    def execute(
        self,
        *_fields: str,
        connection: SalesforceClient | str | None = None
    ) -> QueryResult[_SObject]:
        """
        Executes the SOQL query and returns the first batch of results (up to 2000 records).
        """
        if _fields:
            fields = list(_fields)
        else:
            fields = self.fields

        if isinstance(connection, str):
            client = SalesforceClient.get_connection(connection)
        elif isinstance(connection, SalesforceClient):
            client = connection
        else:
            client = self._sf_connection()

        result: QueryResultJSON
        assert not (self.sobject_type.attributes.tooling and self._include_deleted), (
            "Tooling API does not support query deleted records (QueryAll)"
        )
        if self.sobject_type.attributes.tooling:
            url = f"{client.data_url}/tooling/query/"
        elif self._include_deleted:
            url = f"{client.data_url}/queryAll/"
        else:
            url = f"{client.data_url}/query/"
        result = client.get(url, params={"q": self.format(fields)}).json()
        batch = QueryResultBatch(self.sobject_type, connection=client, **result)  # type: ignore

        return QueryResult([batch])

    def __iter__(self):
        return self.execute()

    def __aiter__(self):
        result = self.execute()
        result.schedule_async_tasks()
        return result
