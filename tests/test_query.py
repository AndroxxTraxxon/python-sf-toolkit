from unittest.mock import AsyncMock, Mock
import pytest
from datetime import datetime, date

from sf_toolkit.data.fields import DateField, IdField, IntField, ListField, NumberField, TextField
from sf_toolkit.data.query_builder import AND, EQ, GT, OR, QueryResult, SoqlQuery, Order
from sf_toolkit.data.sobject import SObject, SObjectList
from .unit_test_models import Opportunity, Account


@pytest.fixture
def mock_query_response(mock_sf_client):
    """Creates a mock response for query results"""
    return {
        "done": True,
        "totalSize": 2,
        "records": [
            {
                "attributes": {"type": "Account"},
                "Id": "001XX000003DGTYAA4",
                "Name": "Test Account 1",
                "Industry": "Technology",
                "AnnualRevenue": 1000000.0,
            },
            {
                "attributes": {"type": "Account"},
                "Id": "001XX000003DGTZBZ4",
                "Name": "Test Account 2",
                "Industry": "Healthcare",
                "AnnualRevenue": 2000000.0,
            },
        ],
    }


@pytest.fixture
def mock_query_response_with_next(mock_sf_client):
    """Creates a mock response for query results with next records URL"""
    return {
        "done": False,
        "totalSize": 4,
        "nextRecordsUrl": "/services/data/v63.0/query/01gRO0000016PIAYA2-500",
        "records": [
            {
                "attributes": {"type": "Account"},
                "Id": "001XX000003DGTYAA4",
                "Name": "Test Account 1",
                "Industry": "Technology",
            },
            {
                "attributes": {"type": "Account"},
                "Id": "001XX000003DGTZBZ4",
                "Name": "Test Account 2",
                "Industry": "Healthcare",
            },
        ],
    }


def test_simple_query_construction():
    """Test basic query construction without conditions"""
    query = SoqlQuery(Account)

    # Basic query should include SELECT and FROM
    query_str = str(query)
    assert "SELECT" in query_str
    assert "FROM Account" in query_str

    # Should include all fields
    for field in Account.keys():
        assert field in query_str


def test_query_with_where_condition():
    """Test query construction with WHERE clause"""
    query = SoqlQuery(Account)
    query.where(Industry="Technology")

    query_str = str(query)
    assert "WHERE Industry = 'Technology'" in query_str


def test_query_with_comparison_operators():
    """Test query construction with different comparison operators"""
    query = SoqlQuery(Account)
    query.where(AnnualRevenue__gt=1000000)  # Greater than

    query_str = str(query)
    assert "WHERE AnnualRevenue > 1000000" in query_str

    # Test multiple conditions
    query = SoqlQuery(Account)
    query.where(AnnualRevenue__gt=1000000, Industry="Technology")

    query_str = str(query)
    assert "WHERE" in query_str
    assert "AnnualRevenue > 1000000" in query_str
    assert "Industry = 'Technology'" in query_str
    assert "AND" in query_str


def test_query_with_like_operator():
    """Test query construction with LIKE operator"""
    query = SoqlQuery(Account)
    query.where(Name__like="Test%")

    query_str = str(query)
    assert "WHERE Name LIKE 'Test%'" in query_str


def test_query_with_in_operator():
    """Test query construction with IN operator"""
    query = SoqlQuery(Account)
    query.where(Industry__in=["Technology", "Healthcare"])

    query_str = str(query)
    assert "WHERE Industry IN ('Technology','Healthcare')" in query_str


def test_query_execution(mock_sf_client, mock_query_response):
    """Test query execution and result handling"""
    # Set up mock response
    mock_sf_client.get.return_value.json.return_value = mock_query_response

    # Create and execute query
    query = SoqlQuery(Account)
    results = query.execute()

    # Verify response handling
    assert isinstance(results, QueryResult)
    assert results.done is True
    assert len(results) == 2
    assert len(results.batches[0].records) == 2

    # Verify record content
    record = next(results)
    assert isinstance(record, Account)
    assert record.Name == "Test Account 1"
    assert record.Industry == "Technology"
    assert record.AnnualRevenue == 1000000.0


def test_query_with_group_by(mock_sf_client):
    """Test query construction with GROUP BY clause"""
    query = SoqlQuery(Account)
    query.group_by("Industry")

    query_str = str(query)
    assert "GROUP BY Industry" in query_str


def test_query_with_order_by():
    """Test query construction with ORDER BY clause"""
    query = SoqlQuery(Account)
    query.order_by(Order("Name", "DESC"), Id="ASC")

    query_str = str(query)
    assert "ORDER BY Name DESC, Id ASC" in query_str


def test_query_with_limit():
    """Test query construction with LIMIT clause"""
    query = SoqlQuery(Account)
    query.limit(10)

    query_str = str(query)
    assert "LIMIT 10" in query_str


def test_query_with_offset():
    """Test query construction with OFFSET clause"""
    query = SoqlQuery(Account)
    query.offset(20)

    query_str = str(query)
    assert "OFFSET 20" in query_str


def test_query_more_results(mock_sf_client, mock_query_response_with_next):
    """Test fetching additional results with query_more"""
    # Setup initial response
    mock_sf_client.get.return_value.json.side_effect = [
        mock_query_response_with_next,
        {
            "done": True,
            "totalSize": 4,
            "records": [
                {
                    "attributes": {"type": "Account"},
                    "Id": "001XX000003DGTYAA5",
                    "Name": "Test Account 3",
                    "Industry": "Retail",
                },
                {
                    "attributes": {"type": "Account"},
                    "Id": "001XX000003DGTZBZ6",
                    "Name": "Test Account 4",
                    "Industry": "Manufacturing",
                },
            ],
        },
    ]

    # Execute initial query
    query = SoqlQuery(Account)
    result = query.execute()

    # Verify initial results
    assert not result.done
    assert len(result) == 4
    assert len(result.batches[-1].records) == 2
    assert result.batches[-1].nextRecordsUrl is not None

    # Get more results
    more_results = result.batches[-1].query_more()

    # Verify additional results
    assert more_results.done
    assert len(more_results.records) == 2
    assert more_results.records[0].Name == "Test Account 3"
    assert more_results.records[1].Industry == "Manufacturing"


def test_query_more_without_next_url(mock_sf_client, mock_query_response):
    """Test query_more when there are no more results"""
    mock_sf_client.get.return_value.json.return_value = mock_query_response

    query = SoqlQuery(Account)
    result = query.execute()

    # Should raise ValueError when trying to get more results
    with pytest.raises(
        ValueError, match="Cannot get more records without nextRecordsUrl"
    ):
        result.batches[-1].query_more()


def test_count_query(mock_sf_client):
    """Test count query execution"""
    # Setup mock response for count query
    mock_sf_client.get.return_value.json.return_value = {
        "done": True,
        "totalSize": 1,
        "records": [{"expr0": 42}],
    }

    query = SoqlQuery(Account)
    count = query.count()

    assert count == 1
    mock_sf_client.get.assert_called_once()

    # Verify COUNT() was used in the query
    call_args = mock_sf_client.get.call_args
    assert "SELECT COUNT()" in call_args[1]["params"]["q"]


def test_boolean_operations():
    """Test complex boolean operations in queries"""
    query = SoqlQuery(Account)
    query.where(
        OR(
            EQ("Industry", "Technology"),
            AND(GT("AnnualRevenue", 1000000), GT("NumberOfEmployees", 100)),
        )
    )

    query_str = str(query)
    assert "WHERE" in query_str
    assert "Industry = 'Technology'" in query_str
    assert "OR" in query_str
    assert "AnnualRevenue > 1000000" in query_str
    assert "NumberOfEmployees > 100" in query_str
    assert "AND" in query_str


def test_query_with_datetime():
    """Test query construction with datetime values"""
    test_date = datetime(2023, 1, 15, 12, 30, 45).astimezone()
    query = Account.query().where(CreatedDate__gt=test_date)

    query_str = str(query)
    assert "WHERE CreatedDate > " in query_str


def test_query_with_date():
    """Test query construction with date values"""
    test_date = date(2023, 1, 15)

    # Create a test with Opportunity since it has DateField
    query = Opportunity.query().where(CloseDate=test_date)

    query_str = str(query)
    assert "WHERE CloseDate = 2023-01-15" in query_str


def test_query_with_raw_where():
    """Test query construction with raw WHERE clause"""
    where_clause = "Name LIKE 'Test%' AND CreatedDate = LAST_N_DAYS:30"
    query = Account.query().where(where_clause)

    query_str = str(query)
    assert where_clause in query_str


def test_query_with_having(mock_sf_client):
    """Test query with HAVING clause"""
    query = Account.query().group_by("Industry").having(AnnualRevenue__gt=1000000)
    assert "GROUP BY Industry" in str(query)
    # Should raise error if HAVING is used without GROUP BY
    with pytest.raises(TypeError, match="Cannot use HAVING statement without GROUP BY"):
        str(Account.query().having(AnnualRevenue__gt=1000000))


def test_query_with_and_having():
    """Test query with multiple HAVING conditions using and_having"""
    query = (
        Account.query()
        .group_by("Industry")
        .having(COUNT__Id__gt=5)
        .and_having(SUM__AnnualRevenue__gt=1000000)
    )

    query_str = str(query)
    assert "GROUP BY Industry" in query_str
    assert "HAVING COUNT(Id) > 5" in query_str
    assert "AND SUM(AnnualRevenue) > 1000000" in query_str


def test_query_with_or_having():
    """Test query with OR condition in HAVING clause"""
    query = (
        Account.query()
        .group_by("Industry")
        .having(COUNT__Id__gt=10)
        .or_having(SUM__AnnualRevenue__gt=5000000)
    )

    query_str = str(query)
    assert "GROUP BY Industry" in query_str
    assert "HAVING COUNT(Id) > 10" in query_str
    assert "OR SUM(AnnualRevenue) > 5000000" in query_str


def test_query_with_chained_having_conditions():
    """Test query with chained HAVING conditions (AND and OR)"""
    query = (
        Account.query()
        .group_by("Industry")
        .having(COUNT__Id__gt=5)
        .and_having(AVG__AnnualRevenue__gt=100000)
        .or_having(SUM__AnnualRevenue__gt=10000000)
    )

    query_str = str(query)
    assert "GROUP BY Industry" in query_str
    assert "HAVING" in query_str
    assert "COUNT(Id) > 5 AND AVG(AnnualRevenue) > 100000" in query_str
    assert "OR SUM(AnnualRevenue) > 10000000" in query_str


def test_query_tooling_api(mock_sf_client):
    """Test query execution against tooling API"""

    # Create a class with tooling API flag
    class ToolingObject(SObject, tooling=True):
        Id = IdField()
        Name = TextField()

    try:
        # Setup mock response
        mock_sf_client.get.return_value.json.return_value = {
            "done": True,
            "totalSize": 1,
            "records": [
                {
                    "attributes": {"type": "ToolingObject"},
                    "Id": "001XX000003DGTYAA4",
                    "Name": "Test Tooling Object",
                }
            ],
        }

        # Execute query
        results = ToolingObject.query().execute()

        # Verify tooling API endpoint was used
        mock_sf_client.get.assert_called_once()
        call_args = mock_sf_client.get.call_args
        assert "tooling/query" in call_args[0][0]

        # Verify results
        assert isinstance(results, QueryResult)
        assert isinstance(results.batches[0].records, SObjectList)
        assert len(results.batches[0].records) == 1
        assert results.batches[0].records[0].Id == "001XX000003DGTYAA4"
        assert results.batches[0].records[0].Name == "Test Tooling Object"

    finally:
        ToolingObject._unregister_()


def test_query_with_field_subquery():
    """Test query construction with field subquery"""
    # Test a query that includes a related list subquery

    class Opportunity(SObject):
        Id = IdField()
        Name = TextField()
        Amount = NumberField()
        CloseDate = DateField()

    class Account(SObject):
        Id = IdField()
        Name = TextField()
        Amount = NumberField()
        CloseDate = DateField()
        Opportunities = ListField(Opportunity)

    query = Account.query().filter_subqueries(
        Opportunities=Opportunity.query().where(StageName="Closed Won")
    )

    query_str = str(query)
    assert "SELECT" in query_str
    assert "FROM Account" in query_str
    assert "FROM Opportunities WHERE StageName = 'Closed Won')" in query_str

    Account._unregister_()
    Opportunity._unregister_()

def test_query_with_nested_field_subquery():
    """Test query construction with nested field subqueries"""
    # Create a more complex query with multiple nested subqueries
    class Contact(SObject):
        Id = IdField()
        Email = TextField()


    class Opportunity(SObject):
        Id = IdField()
        Name = TextField()

    class Account(SObject):
        Id = IdField()
        Name = TextField()
        Opportunities = ListField(Opportunity)
        Contacts = ListField(Contact)

    opportunities_subquery = Opportunity.query().where(Amount__gt=10000)
    try:
        query = Account.query().filter_subqueries(
            Opportunities=opportunities_subquery,
            Contacts=Contact.query().where(Email__like="%@example.com")
        )

        query_str = str(query)
        assert "SELECT Id, Name" in query_str
        assert "(SELECT Id, Name FROM Opportunities WHERE Amount > 10000)" in query_str
        assert "(SELECT Id, Email FROM Contacts WHERE Email LIKE '%@example.com')" in query_str
    finally:
        Account._unregister_()
        Opportunity._unregister_()
        Contact._unregister_()


def test_query_with_where_subquery():
    """Test query construction with WHERE clause containing a subquery"""
    # Test a query that uses a subquery in the WHERE clause

    class Opportunity(SObject):
        AccountId = IdField()

    class Account(SObject):
        Id = IdField()
        Name = TextField()

    try:
        query = Account.query().where(
            Id__in=Opportunity.query().where(Amount__gt=50000)
        )
        query_str = str(query)
        assert "FROM Account WHERE Id IN (SELECT AccountId FROM Opportunity WHERE Amount > 50000)" in query_str

    finally:
        Account._unregister_()
        Opportunity._unregister_()

def test_query_with_complex_where_subquery():
    """Test query construction with complex WHERE clause subquery"""

    class Opportunity(SObject):
        AccountId=IdField()

    class Account(SObject):
        Id=IdField()
        Name=TextField()
        Industry=TextField()

    opportunity_subquery = (
        Opportunity.query()
        .where(CloseDate__gt=date(2023, 1, 1))
        .and_where(StageName="Closed Won")
        .group_by("AccountId")
        .having(SUM__Amount__gt=100000)
    )

    query = Account.query().where(
        Industry__in=["Technology", "Healthcare"],
        Id__in=opportunity_subquery
    )

    query_str = str(query)
    assert "WHERE" in query_str
    assert "Industry IN ('Technology','Healthcare')" in query_str
    assert "AND Id IN (" in query_str
    assert "SELECT AccountId FROM Opportunity" in query_str
    assert "WHERE CloseDate > 2023-01-01 AND StageName = 'Closed Won'" in query_str
    assert "GROUP BY AccountId" in query_str
    assert "HAVING SUM(Amount) > 100000" in query_str


def test_execution_with_field_subquery(mock_sf_client):
    """Test execution of a query with field subquery"""
    # Mock response with subquery results
    mock_sf_client.get.return_value.json.return_value = {
        "done": True,
        "totalSize": 1,
        "records": [
            {
                "attributes": {"type": "Account"},
                "Id": "001XX000003DGTYAA4",
                "Name": "Test Account",
                "Opportunities": {
                    "totalSize": 2,
                    "records": [
                        {
                            "attributes": {"type": "Opportunity"},
                            "Id": "006XX000004DGTYAA4",
                            "Name": "Opp 1",
                            "Amount": 75000
                        },
                        {
                            "attributes": {"type": "Opportunity"},
                            "Id": "006XX000004DGTYBZ4",
                            "Name": "Opp 2",
                            "Amount": 125000
                        }
                    ]
                }
            }
        ]
    }

    class Opportunity(SObject):
        Id=IdField()
        Name=TextField()
        Amount=IntField()

    class Account(SObject):
        Id=IdField()
        Name=TextField()
        Opportunities=ListField(Opportunity)


    # Create a query with a subquery
    query = Account.query()


    # Execute the query
    results = query.execute()

    # Verify the results
    assert len(results) == 1
    account = next(results)
    assert account.Name == "Test Account"
    assert hasattr(account, "Opportunities")
    assert len(account.Opportunities) == 2
    assert account.Opportunities[0].Name == "Opp 1"
    assert account.Opportunities[1].Amount == 125000


def test_query_result_iterator(mock_sf_client, mock_query_response_with_next):
    """Test QueryResult iterator functionality"""
    # Setup mock responses - first batch and second batch
    mock_sf_client.get.return_value.json.side_effect = [
        mock_query_response_with_next,
        {
            "done": True,
            "totalSize": 4,
            "records": [
                {
                    "attributes": {"type": "Account"},
                    "Id": "001XX000003DGTYAA5",
                    "Name": "Test Account 3",
                    "Industry": "Retail",
                },
                {
                    "attributes": {"type": "Account"},
                    "Id": "001XX000003DGTZBZ6",
                    "Name": "Test Account 4",
                    "Industry": "Manufacturing",
                },
            ],
        },
    ]

    # Execute initial query
    query = SoqlQuery(Account)
    results = query.execute()

    # Use the iterator to get all records
    record_list = []
    for record in results:
        record_list.append(record)

    # Verify all 4 records were retrieved through iteration
    assert len(record_list) == 4
    assert record_list[0].Name == "Test Account 1"
    assert record_list[2].Name == "Test Account 3"
    assert record_list[3].Industry == "Manufacturing"


def test_query_result_list_conversion(mock_sf_client, mock_query_response_with_next):
    """Test converting QueryResult to a list"""
    # Setup mock responses
    mock_sf_client.get.return_value.json.side_effect = [
        mock_query_response_with_next,
        {
            "done": True,
            "totalSize": 4,
            "records": [
                {
                    "attributes": {"type": "Account"},
                    "Id": "001XX000003DGTYAA5",
                    "Name": "Test Account 3",
                    "Industry": "Retail",
                },
                {
                    "attributes": {"type": "Account"},
                    "Id": "001XX000003DGTZBZ6",
                    "Name": "Test Account 4",
                    "Industry": "Manufacturing",
                },
            ],
        },
    ]

    # Execute query and convert result to list
    query = SoqlQuery(Account)
    results = query.execute()

    # Convert to list (should handle pagination automatically)
    all_records = list(results)

    # Verify all records were included
    assert len(all_records) == 4
    assert all_records[0].Id == "001XX000003DGTYAA4"
    assert all_records[3].Id == "001XX000003DGTZBZ6"


@pytest.mark.asyncio
async def test_query_result_async_iterator(mock_sf_client, mock_query_response_with_next):
    """Test QueryResult async iterator functionality"""
    # Setup mock responses
    mock_sf_client.get.return_value.json.return_value = mock_query_response_with_next
    mock_sf_client.as_async.get = (async_get := AsyncMock())
    async_get.return_value = Mock()
    async_get.return_value.json.return_value = {
        "done": True,
        "totalSize": 4,
        "records": [
            {
                "attributes": {"type": "Account"},
                "Id": "001XX000003DGTYAA5",
                "Name": "Test Account 3",
                "Industry": "Retail",
            },
            {
                "attributes": {"type": "Account"},
                "Id": "001XX000003DGTZBZ6",
                "Name": "Test Account 4",
                "Industry": "Manufacturing",
            },
        ],
    }
    # Execute query
    query = SoqlQuery(Account)
    results = query.execute()

    # Use async iterator
    records = []
    async for record in results:
        records.append(record)

    # Verify all records were retrieved
    assert len(records) == 4
    assert records[0].Name == "Test Account 1"
    assert records[1].Name == "Test Account 2"
    assert records[2].Name == "Test Account 3"
    assert records[3].Name == "Test Account 4"
