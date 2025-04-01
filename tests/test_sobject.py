import pytest
from unittest.mock import MagicMock, patch
import datetime
from salesforce_toolkit.data.sobject import SObject, MultiPicklistField
from salesforce_toolkit.data.query_builder import SoqlSelect
from salesforce_toolkit.client import SalesforceClient


@pytest.fixture
def mock_sf_client():
    # Create a mock SalesforceClient for testing
    mock_client = MagicMock(spec=SalesforceClient)
    mock_client.sobjects_url = "/services/data/v57.0/sobjects"
    mock_client.data_url = "/services/data/v57.0/query"
    mock_client.composite_sobjects_url = MagicMock(return_value="/services/data/v57.0/composite/sobjects/Account")

    # Store the original get_connection method
    original_get_connection = SalesforceClient.get_connection

    # Override the get_connection method to return our mock
    SalesforceClient.get_connection = MagicMock(return_value=mock_client)

    yield mock_client

    # Restore the original get_connection method
    SalesforceClient.get_connection = original_get_connection


def test_sobject_class_definition():
    # Define an SObject subclass
    class Account(SObject, api_name="Account"):
        Id: str
        Name: str
        Industry: str
        AnnualRevenue: float
        CreatedDate: datetime.datetime
        LastModifiedDate: datetime.datetime
        IsActive: bool
        Tags: MultiPicklistField

    # Test basic class properties
    assert Account._sf_attrs.type == "Account"
    assert set(Account.fields().keys()) == {
        'Id', 'Name', 'Industry', 'AnnualRevenue', 'CreatedDate',
        'LastModifiedDate', 'IsActive', 'Tags'
    }

    # Test instance creation
    account = Account(
        Id="001XX000003DGT2IAO",
        Name="Acme Corp",
        Industry="Technology",
        AnnualRevenue=1000000.0,
        CreatedDate=datetime.datetime(2023, 1, 1, 12, 0, 0),
        LastModifiedDate=datetime.datetime(2023, 1, 2, 12, 0, 0),
        IsActive=True,
        Tags="cloud;technology;partner"
    )

    # Test attribute access
    assert account.Id == "001XX000003DGT2IAO"
    assert account.Name == "Acme Corp"
    assert account.AnnualRevenue == 1000000.0
    assert account.IsActive is True
    assert account.Tags.values == ["cloud", "technology", "partner"]

    # Test dict-style access
    assert account['Name'] == "Acme Corp"


@patch('salesforce_toolkit.client.SalesforceClient.get')
def test_sobject_get(mock_get):
    # Define an SObject subclass
    class Contact(SObject, api_name="Contact"):
        Id: str
        FirstName: str
        LastName: str
        Email: str
        Birthdate: datetime.date

    # Mock the response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "attributes": {"type": "Contact"},
        "Id": "003XX000004UINIAA4",
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@example.com",
        "Birthdate": "1980-01-15"
    }
    mock_get.return_value = mock_response

    # Call get method
    contact = Contact.read("003XX000004UINIAA4")

    # Verify the result
    assert contact.Id == "003XX000004UINIAA4"
    assert contact.FirstName == "John"
    assert contact.LastName == "Doe"
    assert contact.Email == "john.doe@example.com"
    assert contact.Birthdate == datetime.date(1980, 1, 15)

    # Verify the API call
    mock_get.assert_called_once()


@patch('salesforce_toolkit.client.SalesforceClient.post')
def test_sobject_fetch(mock_post):
    # Define an SObject subclass
    class Opportunity(SObject, api_name="Opportunity"):
        Id: str
        Name: str
        Amount: float
        CloseDate: datetime.date
        StageName: str

    # Mock the response
    mock_response = MagicMock()
    mock_response.text = '''[
        {
            "attributes": {"type": "Opportunity"},
            "Id": "006XX000004UvVtIAK",
            "Name": "Big Deal",
            "Amount": 50000.0,
            "CloseDate": "2023-06-30",
            "StageName": "Closed Won"
        },
        {
            "attributes": {"type": "Opportunity"},
            "Id": "006XX000004UvVuIAK",
            "Name": "Bigger Deal",
            "Amount": 100000.0,
            "CloseDate": "2023-07-15",
            "StageName": "Negotiation"
        }
    ]'''
    mock_post.return_value = mock_response

    # Call fetch method
    opportunities = Opportunity.list(
        "006XX000004UvVtIAK",
        "006XX000004UvVuIAK"
    )

    # Verify the results
    assert len(opportunities) == 2
    assert opportunities[0].Id == "006XX000004UvVtIAK"
    assert opportunities[0].Name == "Big Deal"
    assert opportunities[0].Amount == 50000.0
    assert opportunities[1].Id == "006XX000004UvVuIAK"
    assert opportunities[1].Name == "Bigger Deal"
    assert opportunities[1].StageName == "Negotiation"

    # Verify the API call
    mock_post.assert_called_once()


@patch('salesforce_toolkit.client.SalesforceClient.get')
def test_sobject_describe(mock_get):
    # Define an SObject subclass
    class Lead(SObject, api_name="Lead"):
        Id: str
        FirstName: str
        LastName: str
        Company: str
        Status: str

    # Mock the response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "Lead",
        "label": "Lead",
        "labelPlural": "Leads",
        "fields": [
            {
                "name": "Id",
                "type": "id",
                "label": "Lead ID"
            },
            {
                "name": "FirstName",
                "type": "string",
                "label": "First Name"
            }
        ]
    }
    mock_get.return_value = mock_response

    # Call describe method
    describe_result = Lead.describe()

    # Verify the result
    assert describe_result["name"] == "Lead"
    assert describe_result["labelPlural"] == "Leads"
    assert len(describe_result["fields"]) == 2

    # Verify the API call
    mock_get.assert_called_once()


@patch('salesforce_toolkit.client.SalesforceClient.get')
def test_from_description(mock_get):
    # Mock the describe API response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "CustomObject__c",
        "label": "Custom Object",
        "labelPlural": "Custom Objects",
        "fields": [
            {
                "name": "Id",
                "type": "id",
                "label": "Record ID"
            },
            {
                "name": "Name",
                "type": "string",
                "label": "Name"
            },
            {
                "name": "CustomDate__c",
                "type": "date",
                "label": "Custom Date"
            },
            {
                "name": "IsActive__c",
                "type": "boolean",
                "label": "Is Active"
            },
            {
                "name": "Categories__c",
                "type": "multipicklist",
                "label": "Categories"
            }
        ]
    }
    mock_get.return_value = mock_response

    # Generate SObject class from description
    CustomObject = SObject.from_description("CustomObject__c")

    # Verify the class was created correctly
    assert CustomObject._sf_attrs.type == "CustomObject__c"
    assert set(CustomObject.fields().keys()) == {
        'Id', 'Name', 'CustomDate__c', 'IsActive__c', 'Categories__c'
    }
    assert CustomObject.fields()['CustomDate__c'] is datetime.date
    assert CustomObject.fields()['IsActive__c'] is bool
    assert CustomObject.fields()['Categories__c'] is MultiPicklistField

    # Create an instance
    obj = CustomObject(
        Id="a01XX000003GabcIAC",
        api_name="Test Custom Object",
        CustomDate__c="2023-01-15",
        IsActive__c=True,
        Categories__c="one;two;three"
    )

    # Verify instance data
    assert obj.Id == "a01XX000003GabcIAC"  # type: ignore
    assert obj.CustomDate__c == datetime.date(2023, 1, 15)  # type: ignore
    assert obj.IsActive__c is True  # type: ignore
    assert isinstance(obj.Categories__c, MultiPicklistField)  # type: ignore
    assert obj.Categories__c.values == ["one", "two", "three"]  # type: ignore


@patch('salesforce_toolkit.client.SalesforceClient.get')
def test_query_builder(mock_get):
    # Define an SObject subclass
    class Case(SObject, api_name="Case"):
        Id: str
        Subject: str
        Description: str
        Status: str
        Priority: str
        CreatedDate: datetime.datetime

    # Mock the response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "done": True,
        "totalSize": 2,
        "records": [
            {
                "attributes": {"type": "Case"},
                "Id": "500XX000001MxWtIAK",
                "Subject": "Case 1",
                "Status": "New",
                "Priority": "High"
            },
            {
                "attributes": {"type": "Case"},
                "Id": "500XX000001MxWuIAK",
                "Subject": "Case 2",
                "Status": "Working",
                "Priority": "Medium"
            }
        ]
    }
    mock_get.return_value = mock_response

    # Create a query
    query = SoqlSelect(Case)

    # Execute the query
    results = query.query(["Id", "Subject", "Status", "Priority"])

    # Verify the results
    assert results.totalSize == 2
    assert len(results.records) == 2
    assert results.records[0].Id == "500XX000001MxWtIAK"
    assert results.records[0].Subject == "Case 1"
    assert results.records[0].Status == "New"
    assert results.records[1].Priority == "Medium"

    # Verify the API call
    mock_get.assert_called_once()
