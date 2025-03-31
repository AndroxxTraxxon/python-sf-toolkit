"""Tests for salesforce_toolkit.formatting."""
import pytest
from datetime import datetime, date, timezone
from salesforce_toolkit.formatting import (
    quote_soql_value,
    format_soql,
    format_external_id,
    format_datetime,
    parse_datetime
)


def test_quote_soql_string():
    """Test quoting a string."""
    assert quote_soql_value("hello") == "'hello'"
    assert quote_soql_value("it's") == "'it\\'s'"
    assert quote_soql_value('with "quotes"') == "'with \\\"quotes\\\"'"
    assert quote_soql_value("with \n newline") == "'with \\n newline'"
    assert quote_soql_value("with \r return") == "'with \\r return'"
    assert quote_soql_value("with \t tab") == "'with \\t tab'"
    assert quote_soql_value("with \b backspace") == "'with \\b backspace'"
    assert quote_soql_value("with \f formfeed") == "'with \\f formfeed'"
    assert quote_soql_value("with \\ backslash") == "'with \\\\ backslash'"


def test_quote_soql_boolean():
    """Test quoting booleans."""
    assert quote_soql_value(True) == "TRUE"
    assert quote_soql_value(False) == "FALSE"


def test_quote_soql_none():
    """Test quoting None."""
    assert quote_soql_value(None) == "NULL"


def test_quote_soql_numbers():
    """Test quoting numbers."""
    assert quote_soql_value(42) == "42"
    assert quote_soql_value(3.14) == "3.14"


def test_quote_soql_collections():
    """Test quoting collections."""
    assert quote_soql_value([1, 2, 3]) == "(1,2,3)"
    assert quote_soql_value(("a", "b")) == "('a','b')"
    assert quote_soql_value({"x", "y"}) in ("('x','y')", "('y','x')")


def test_quote_soql_datetime():
    """Test quoting datetime objects."""
    dt = datetime(2023, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
    assert quote_soql_value(dt) == "2023-01-15T12:30:45+00:00"

    # Test naive datetime gets converted to UTC
    naive_dt = datetime(2023, 1, 15, 12, 30, 45)
    quoted = quote_soql_value(naive_dt)
    assert "+00:00" in quoted
    assert "2023-01-15" in quoted

    # Test microseconds are stripped
    dt_with_micro = datetime(2023, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
    assert quote_soql_value(dt_with_micro) == "2023-01-15T12:30:45+00:00"


def test_quote_soql_date():
    """Test quoting date objects."""
    d = date(2023, 1, 15)
    assert quote_soql_value(d) == "2023-01-15"


def test_quote_soql_invalid():
    """Test quoting invalid types raises ValueError."""
    with pytest.raises(ValueError):
        quote_soql_value(object())


def test_format_soql():
    """Test formatting SOQL queries."""
    # Test basic formatting
    assert format_soql("SELECT Id FROM Account WHERE Name = {}", "Test") == "SELECT Id FROM Account WHERE Name = 'Test'"

    # Test with named parameters
    assert format_soql("SELECT Id FROM Contact WHERE FirstName = {first} AND LastName = {last}",
                       first="John", last="Doe") == "SELECT Id FROM Contact WHERE FirstName = 'John' AND LastName = 'Doe'"

    # Test with literal format spec
    assert format_soql("SELECT {0:literal} FROM Account", "COUNT(Id)") == "SELECT COUNT(Id) FROM Account"

    # Test with LIKE format spec
    assert format_soql("SELECT Id FROM Account WHERE Name LIKE '%{0:like}%'", "100%") == "SELECT Id FROM Account WHERE Name LIKE '%100\\%%'"

    # Test with lists
    assert format_soql("SELECT Id FROM Account WHERE Id IN {}", [1, 2, 3]) == "SELECT Id FROM Account WHERE Id IN (1,2,3)"


def test_format_external_id():
    """Test formatting external IDs."""
    assert format_external_id("CustomField__c", "12345") == "CustomField__c/12345"
    assert format_external_id("Email__c", "user@example.com") == "Email__c/user%40example.com"
    assert format_external_id("Path__c", "a/b/c") == "Path__c/a%2Fb%2Fc"


def test_format_datetime():
    """Test formatting datetime objects."""
    dt = datetime(2023, 1, 15, 12, 30, 45, 123456, tzinfo=timezone.utc)
    formatted_dt = format_datetime(dt)
    assert formatted_dt == "2023-01-15T12:30:45.123456+0000" or formatted_dt.startswith("2023-01-15T12:30:45.123456")

    # Test naive datetime
    naive_dt = datetime(2023, 1, 15, 12, 30, 45, 123456)
    formatted = format_datetime(naive_dt)
    # Just check that the datetime was formatted correctly and has timezone info
    assert formatted.startswith("2023-01-15T12:30:45.123456")
    assert "+" in formatted or "-" in formatted  # Check timezone was added


def test_parse_datetime():
    """Test parsing datetime strings."""
    dt_str = "2023-01-15T12:30:45.123456+0000"
    dt = parse_datetime(dt_str)

    assert dt.year == 2023
    assert dt.month == 1
    assert dt.day == 15
    assert dt.hour == 12
    assert dt.minute == 30
    assert dt.second == 45
    assert dt.microsecond == 123456
    assert dt.tzinfo is not None  # Should have timezone info
