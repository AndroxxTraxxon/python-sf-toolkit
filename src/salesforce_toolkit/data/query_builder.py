from typing import Literal, NamedTuple
from datetime import datetime, date

from sf_toolkit.formatting import quote_soql_value

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


class SoqlSelect:
    fields: list[str]
    sobject: str
    where: Comparison | BooleanOperator | None
    grouping: list[str] | None
    having: Comparison | BooleanOperator | None
    limit: int | None
    offset: int | None
    order: list[Order] | None

    def __str__(self):
        segments = ["SELECT", ", ".join(self.fields), f"FROM {self.sobject}"]
        if self.where:
            segments.append(str(self.where))
        if self.grouping:
            segments.extend(["GROUP BY", ", ".join(self.grouping)])
        if self.having:
            if self.grouping is None:
                raise TypeError("Cannot use HAVING statement without GROUP BY")

        return " ".join(segments)
