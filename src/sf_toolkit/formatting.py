"""Formatting helpers that perform quoting and escaping"""

import urllib.parse
from datetime import date, datetime, timezone
from string import Formatter

# https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/sforce_api_calls_soql_select_quotedstringescapes.htm
soql_escapes = str.maketrans(
    {
        "\\": "\\\\",
        "'": "\\'",
        '"': '\\"',
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
        "\b": "\\b",
        "\f": "\\f",
    }
)

soql_like_escapes = str.maketrans(
    {
        "%": "\\%",
        "_": "\\_",
    }
)

SF_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class SoqlFormatter(Formatter):
    """Custom formatter to apply quoting or the :literal format spec"""

    def format_field(self, value, format_spec):
        if not format_spec:
            return quote_soql_value(value)
        if format_spec == "literal":
            # literal: allows circumventing everything while still using
            # the same format string
            return value
        if format_spec == "like":
            # like: allows escaping substring used in LIKE expression
            # does not quote
            return str(value).translate(soql_escapes).translate(soql_like_escapes)
        return super().format_field(value, format_spec)


def format_soql(query, *args, **kwargs):
    """Insert values quoted for SOQL into a format string"""
    return SoqlFormatter().vformat(query, args, kwargs)


# pylint: disable=too-many-return-statements
def quote_soql_value(value):
    """Quote/escape either an individual value or a list of values
    for a SOQL value expression"""
    if isinstance(value, str):
        return "'" + value.translate(soql_escapes) + "'"
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, set, tuple)):
        quoted_items = [quote_soql_value(member) for member in value]
        return "(" + ",".join(quoted_items) + ")"
    if isinstance(value, datetime):
        # Salesforce spec requires a datetime literal
        # that is not naive and without MS
        value = value.replace(microsecond=0)
        value = value.astimezone(tz=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise ValueError("unquotable value type")


def format_external_id(field, value):
    """Create an external ID string for use with get() or upsert()"""
    return field + "/" + urllib.parse.quote(value, safe="")


def format_datetime(value: datetime):
    """Get the provided datetime as a Salesforce-compliant formatted string"""
    if value.tzinfo is None:
        # just assume the current timezone if there is none
        value = value.astimezone()
    return value.strftime(SF_DATETIME_FORMAT)


def parse_datetime(value: str):
    """Parse a datetime from a Salesforce datetime string value"""
    return datetime.strptime(value, SF_DATETIME_FORMAT)
