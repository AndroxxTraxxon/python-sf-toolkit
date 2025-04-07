import pytest
from unittest.mock import MagicMock, Mock
import datetime
from typing import Final
from sf_toolkit.data.sobject import (
    SObject,
    MultiPicklistField,
    ReadOnlyAssignmentException,
)
from sf_toolkit.data.query_builder import SoqlSelect
from sf_toolkit.client import SalesforceClient
from sf_toolkit.interfaces import I_SalesforceClient


class Opportunity(SObject):
    Id: str
    Name: str
    Amount: float
    CloseDate: datetime.date
    StageName: str


class Account(SObject):
    Id: str
    Name: str
    Industry: str
    AnnualRevenue: float
    Description: str
    CreatedDate: Final[datetime.datetime]  # type: ignore
    LastModifiedDate: Final[datetime.datetime]  # type: ignore


@pytest.fixture()
def mock_sf_client():
    # Create a mock SalesforceClient for testing
    mock_client = MagicMock(spec=SalesforceClient)
    mock_client.sobjects_url = "/services/data/v57.0/sobjects"
    mock_client.data_url = "/services/data/v57.0/query"
    mock_client.composite_sobjects_url = MagicMock(
        return_value="/services/data/v57.0/composite/sobjects/Account"
    )

    # Keep a reference to the original _connections dictionary to restore later
    original_connections = I_SalesforceClient._connections

    # Add the mock client to the _connections dictionary directly
    I_SalesforceClient._connections = {
        SalesforceClient.DEFAULT_CONNECTION_NAME: mock_client
    }

    yield mock_client

    # Restore the original _connections dictionary
    I_SalesforceClient._connections = original_connections


def test_sobject_class_definition():
    # Test basic class properties
    assert Account._sf_attrs.type == "Account"
    assert set(Account.fields().keys()) == {
        "Id",
        "Name",
        "Industry",
        "AnnualRevenue",
        "CreatedDate",
        "LastModifiedDate",
        "Description",
    }

    # Test instance creation
    account = Account(
        Id="001XX000003DGT2IAO",
        Name="Acme Corp",
        Industry="Technology",
        AnnualRevenue=1000000.0,
        CreatedDate=(
            cdt := datetime.datetime(2023, 1, 1, 12, 0, 0).astimezone()
        ).isoformat(timespec="milliseconds"),
        LastModifiedDate=(
            lmdt := datetime.datetime(2023, 1, 1, 12, 0, 0).astimezone()
        ).isoformat(timespec="milliseconds"),
        Description="This is a test account.",
    )

    # Test attribute access
    assert account.Id == "001XX000003DGT2IAO"
    assert account.Name == "Acme Corp"
    assert account.AnnualRevenue == 1000000.0
    assert account.Description == "This is a test account."
    assert account.CreatedDate == cdt
    assert account.LastModifiedDate == lmdt

    # Test dict-style access
    assert account["Name"] == "Acme Corp"


def test_sobject_get(mock_sf_client):
    # Define an SObject subclass
    class Contact(SObject):
        Id: str
        FirstName: str
        LastName: str
        Email: str
        Birthdate: datetime.date

    # Mock the response
    mock_response = Mock()
    mock_response.json.return_value = {
        "attributes": {"type": "Contact"},
        "Id": "003XX000004UINIAA4",
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@example.com",
        "Birthdate": "1980-01-15",
    }
    mock_sf_client.get.return_value = mock_response

    # Call get method
    contact = Contact.read("003XX000004UINIAA4")
    # Verify the result
    assert contact.Id == "003XX000004UINIAA4"
    assert contact.FirstName == "John"
    assert contact.LastName == "Doe"
    assert contact.Email == "john.doe@example.com"
    assert contact.Birthdate == datetime.date(1980, 1, 15)

    # Verify the API call
    mock_sf_client.get.assert_called_once()


def test_sobject_fetch(mock_sf_client):
    # Define an SObject subclass

    # Mock the response
    mock_response = MagicMock()
    mock_response.text = """[
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
    ]"""
    mock_sf_client.post.return_value = mock_response

    # Call fetch method
    opportunities = Opportunity.list("006XX000004UvVtIAK", "006XX000004UvVuIAK")

    # Verify the results
    assert len(opportunities) == 2
    assert opportunities[0].Id == "006XX000004UvVtIAK"
    assert opportunities[0].Name == "Big Deal"
    assert opportunities[0].Amount == 50000.0
    assert opportunities[1].Id == "006XX000004UvVuIAK"
    assert opportunities[1].Name == "Bigger Deal"
    assert opportunities[1].StageName == "Negotiation"

    # Verify the API call
    mock_sf_client.post.assert_called_once()


def test_sobject_describe(mock_sf_client):
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
            {"name": "Id", "type": "id", "label": "Lead ID"},
            {"name": "FirstName", "type": "string", "label": "First Name"},
        ],
    }
    mock_sf_client.get.return_value = mock_response

    # Call describe method
    describe_result = Lead.describe()

    # Verify the result
    assert describe_result["name"] == "Lead"
    assert describe_result["labelPlural"] == "Leads"
    assert len(describe_result["fields"]) == 2

    # Verify the API call
    mock_sf_client.get.assert_called_once()


def test_from_description(mock_sf_client):
    # Mock the describe API response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "CustomObject__c",
        "label": "Custom Object",
        "labelPlural": "Custom Objects",
        "fields": [
            {"name": "Id", "type": "id", "label": "Record ID"},
            {"name": "Name", "type": "string", "label": "Name"},
            {"name": "CustomDate__c", "type": "date", "label": "Custom Date"},
            {"name": "IsActive__c", "type": "boolean", "label": "Is Active"},
            {"name": "Categories__c", "type": "multipicklist", "label": "Categories"},
        ],
    }
    mock_sf_client.get.return_value = mock_response

    # Generate SObject class from description
    CustomObject = SObject.from_description("CustomObject__c")

    # Verify the class was created correctly
    assert CustomObject._sf_attrs.type == "CustomObject__c"
    assert set(CustomObject.keys()) == {
        "Id",
        "Name",
        "CustomDate__c",
        "IsActive__c",
        "Categories__c",
    }
    assert CustomObject.fields()["CustomDate__c"] is Final[datetime.date]
    assert CustomObject.fields()["IsActive__c"] is Final[bool]
    assert CustomObject.fields()["Categories__c"] is Final[MultiPicklistField]

    # Create an instance
    obj = CustomObject(
        Id="a01XX000003GabcIAC",
        CustomDate__c="2023-01-15",
        IsActive__c=True,
        Categories__c="one;two;three",
    )

    # Verify instance data
    assert obj.Id == "a01XX000003GabcIAC"  # type: ignore
    assert obj.CustomDate__c == datetime.date(2023, 1, 15)  # type: ignore
    assert obj.IsActive__c is True  # type: ignore
    assert isinstance(obj.Categories__c, MultiPicklistField)  # type: ignore
    assert obj.Categories__c.values == ["one", "two", "three"]  # type: ignore


def test_query_builder(mock_sf_client):
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
                "Priority": "High",
            },
            {
                "attributes": {"type": "Case"},
                "Id": "500XX000001MxWuIAK",
                "Subject": "Case 2",
                "Status": "Working",
                "Priority": "Medium",
            },
        ],
    }
    mock_sf_client.get.return_value = mock_response

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
    mock_sf_client.get.assert_called_once()

    def test_query_builder(mock_sf_client):
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
                    "Priority": "High",
                },
                {
                    "attributes": {"type": "Case"},
                    "Id": "500XX000001MxWuIAK",
                    "Subject": "Case 2",
                    "Status": "Working",
                    "Priority": "Medium",
                },
            ],
        }
        mock_sf_client.get.return_value = mock_response

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
        mock_sf_client.get.assert_called_once()

    def test_save_insert(mock_sf_client):
        """Test the save_insert method for creating a new SObject record"""
        # Create a new account without an ID
        account = Account(
            Name="New Test Account", Industry="Technology", AnnualRevenue=5000000.0
        )

        # Mock the response for the POST request
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "001XX000003DGTNEW",
            "success": True,
            "errors": [],
        }
        mock_sf_client.post.return_value = mock_response

        # Save the account
        account.save_insert()

        # Verify the ID was set on the object
        assert account.Id == "001XX000003DGTNEW"

        # Verify the API call was made correctly
        mock_sf_client.post.assert_called_once()
        args, kwargs = mock_sf_client.post.call_args

        # Check the endpoint
        assert args[0] == "/services/data/v57.0/sobjects/Account"

        # Check the payload doesn't include Id or attributes
        assert "Id" not in kwargs["json"]
        assert "attributes" not in kwargs["json"]
        assert kwargs["json"]["Name"] == "New Test Account"
        assert kwargs["json"]["Industry"] == "Technology"
        assert kwargs["json"]["AnnualRevenue"] == 5000000.0

    def test_save_insert_with_reload(mock_sf_client):
        """Test the save_insert method with reload_after_success=True"""
        # Create a new account without an ID
        account = Account(Name="Test Account with Reload", Industry="Healthcare")

        # Mock the response for the POST request
        post_response = Mock()
        post_response.json.return_value = {
            "id": "001XX000003DGTREL",
            "success": True,
            "errors": [],
        }
        mock_sf_client.post.return_value = post_response

        # Mock the response for the GET request (reload)
        get_response = Mock()
        get_response.json.return_value = {
            "attributes": {"type": "Account"},
            "Id": "001XX000003DGTREL",
            "Name": "Test Account with Reload",
            "Industry": "Healthcare",
            "AnnualRevenue": 7500000.0,
            "Description": "Auto-populated description",
            "CreatedDate": datetime.datetime.now().isoformat(),
            "LastModifiedDate": datetime.datetime.now().isoformat(),
        }
        mock_sf_client.get.return_value = get_response

        # Save the account with reload
        account.save_insert(reload_after_success=True)

        # Verify the ID was set on the object
        assert account.Id == "001XX000003DGTREL"

        # Verify additional fields were populated from the reload
        assert account.AnnualRevenue == 7500000.0
        assert account.Description == "Auto-populated description"

        # Verify both API calls were made
        mock_sf_client.post.assert_called_once()
        mock_sf_client.get.assert_called_once()

    def test_save_update(mock_sf_client):
        """Test the save_update method for updating an existing SObject record"""
        # Create an account with an existing ID
        account = Account(
            Id="001XX000003DGTUPD",
            Name="Existing Account",
            Industry="Retail",
            AnnualRevenue=3000000.0,
        )

        # Clear dirty fields set by initialization
        account._dirty_fields.clear()

        # Make changes to the account
        account.Name = "Updated Account Name"
        account.Industry = "Financial Services"

        # Mock the response for the PATCH request
        mock_response = Mock()
        mock_response.status_code = 204  # No Content success response
        mock_sf_client.patch.return_value = mock_response

        # Update the account
        account.save_update()

        # Verify the API call was made correctly
        mock_sf_client.patch.assert_called_once()
        args, kwargs = mock_sf_client.patch.call_args

        # Check the endpoint includes the ID
        assert args[0] == "/services/data/v57.0/sobjects/Account/001XX000003DGTUPD"

        # Check the payload only includes changed fields
        assert "Id" not in kwargs["json"]
        assert "attributes" not in kwargs["json"]
        assert "AnnualRevenue" not in kwargs["json"]
        assert kwargs["json"]["Name"] == "Updated Account Name"
        assert kwargs["json"]["Industry"] == "Financial Services"

        # Verify dirty fields were cleared
        assert len(account._dirty_fields) == 0

    def test_save_update_only_changes(mock_sf_client):
        """Test the save_update method with only_changes=False to update all fields"""
        # Create an account with an existing ID
        account = Account(
            Id="001XX000003DGTALL",
            Name="Full Update Account",
            Industry="Education",
            AnnualRevenue=1500000.0,
            Description="Original description",
        )

        # Clear dirty fields set by initialization
        account._dirty_fields.clear()

        # Make a single change to the account
        account.Description = "Updated description"

        # Mock the response for the PATCH request
        mock_response = Mock()
        mock_response.status_code = 204
        mock_sf_client.patch.return_value = mock_response

        # Update the account with only_changes=False
        account.save_update(only_changes=False)

        # Verify the API call was made correctly
        mock_sf_client.patch.assert_called_once()
        args, kwargs = mock_sf_client.patch.call_args

        # Check the payload includes all fields (except Id and attributes)
        assert "Id" not in kwargs["json"]
        assert "attributes" not in kwargs["json"]
        assert kwargs["json"]["Name"] == "Full Update Account"
        assert kwargs["json"]["Industry"] == "Education"
        assert kwargs["json"]["AnnualRevenue"] == 1500000.0
        assert kwargs["json"]["Description"] == "Updated description"

    def test_save_upsert(mock_sf_client):
        """Test the save_upsert method using an external ID field"""

        # Define a custom SObject with an external ID field
        class CustomObject(SObject, api_name="CustomObject__c"):
            Id: str
            Name: str
            External_Id__c: str
            Custom_Field__c: str

        # Create an instance with an external ID but no Salesforce ID
        custom_obj = CustomObject(
            Name="Test Upsert",
            External_Id__c="EXT-12345",
            Custom_Field__c="Original Value",
        )

        # Clear dirty fields set by initialization
        custom_obj._dirty_fields.clear()

        # Update a field
        custom_obj.Custom_Field__c = "Updated Value"

        # Mock the response for the PATCH request (successful update)
        mock_response = Mock()
        mock_response.status_code = 204  # No Content (record was updated)
        mock_sf_client.patch.return_value = mock_response

        # Perform the upsert
        custom_obj.save_upsert(external_id_field="External_Id__c")

        # Verify the API call was made correctly
        mock_sf_client.patch.assert_called_once()
        args, kwargs = mock_sf_client.patch.call_args

        # Check the endpoint includes the external ID field and value
        assert (
            args[0]
            == "/services/data/v57.0/sobjects/CustomObject__c/External_Id__c/EXT-12345"
        )

        # Check the payload only includes the changed field
        assert "Id" not in kwargs["json"]
        assert "Name" not in kwargs["json"]
        assert "External_Id__c" not in kwargs["json"]
        assert "attributes" not in kwargs["json"]
        assert kwargs["json"]["Custom_Field__c"] == "Updated Value"

        # Verify dirty fields were cleared
        assert len(custom_obj._dirty_fields) == 0

    def test_save_upsert_insert(mock_sf_client):
        """Test the save_upsert method creating a new record"""

        # Define a custom SObject with an external ID field
        class CustomObject(SObject, api_name="CustomObject__c"):
            Id: str
            Name: str
            External_Id__c: str
            Custom_Field__c: str

        # Create an instance with an external ID but no Salesforce ID
        custom_obj = CustomObject(
            Name="Test Upsert Insert",
            External_Id__c="EXT-NEW-1",
            Custom_Field__c="New Value",
        )

        # Mock the response for the PATCH request (successful insert)
        mock_response = Mock()
        mock_response.status_code = 201  # Created (new record)
        mock_response.json.return_value = {
            "id": "a01XX000003GabcNEW",
            "success": True,
            "errors": [],
        }
        mock_sf_client.patch.return_value = mock_response

        # Perform the upsert
        custom_obj.save_upsert(external_id_field="External_Id__c")

        # Verify the API call was made correctly
        mock_sf_client.patch.assert_called_once()
        args, kwargs = mock_sf_client.patch.call_args

        # Check the endpoint includes the external ID field and value
        assert (
            args[0]
            == "/services/data/v57.0/sobjects/CustomObject__c/External_Id__c/EXT-NEW-1"
        )

        # Verify the ID was set from the response
        assert custom_obj.Id == "a01XX000003GabcNEW"

    def test_save_method_with_id(mock_sf_client):
        """Test the general save method with an existing ID (should use save_update)"""
        # Create an account with an ID
        account = Account(
            Id="001XX000003DGTSAVE", Name="Save Method Test", Industry="Manufacturing"
        )

        # Clear dirty fields set by initialization
        account._dirty_fields.clear()

        # Make a change
        account.Name = "Save Method Updated"

        # Mock the response for the PATCH request
        mock_response = Mock()
        mock_response.status_code = 204
        mock_sf_client.patch.return_value = mock_response

        # Call the general save method
        account.save()

        # Verify update was called (PATCH request)
        mock_sf_client.patch.assert_called_once()
        args, kwargs = mock_sf_client.patch.call_args

        # Check the endpoint includes the ID
        assert args[0] == "/services/data/v57.0/sobjects/Account/001XX000003DGTSAVE"

        # Check payload only contains changed fields
        assert kwargs["json"] == {"Name": "Save Method Updated"}

    def test_save_method_without_id(mock_sf_client):
        """Test the general save method without an ID (should use save_insert)"""
        # Create an account without an ID
        account = Account(Name="New Save Account", Industry="Technology")

        # Mock the response for the POST request
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "001XX000003DGTNEW2",
            "success": True,
            "errors": [],
        }
        mock_sf_client.post.return_value = mock_response

        # Call the general save method
        account.save()

        # Verify insert was called (POST request)
        mock_sf_client.post.assert_called_once()

        # Check the ID was set
        assert account.Id == "001XX000003DGTNEW2"

    def test_save_method_with_external_id(mock_sf_client):
        """Test the general save method with an external ID (should use save_upsert)"""

        # Define a custom SObject with an external ID field
        class CustomObject(SObject, api_name="CustomObject__c"):
            Id: str
            Name: str
            External_Id__c: str
            Description__c: str

        # Create an instance with an external ID but no Salesforce ID
        custom_obj = CustomObject(
            Name="External ID Save Test",
            External_Id__c="EXT-SAVE-1",
            Description__c="Test Description",
        )

        # Mock the response for the PATCH request (successful upsert)
        mock_response = Mock()
        mock_response.status_code = 204  # No Content (updated existing record)
        mock_sf_client.patch.return_value = mock_response

        # Call the general save method with external_id_field parameter
        custom_obj.save(external_id_field="External_Id__c")

        # Verify upsert was called (PATCH request to the external ID endpoint)
        mock_sf_client.patch.assert_called_once()
        args, kwargs = mock_sf_client.patch.call_args

        # Check the endpoint includes the external ID field and value
        assert (
            args[0]
            == "/services/data/v57.0/sobjects/CustomObject__c/External_Id__c/EXT-SAVE-1"
        )

    def test_readonly_assignment_exception():
        """Test that assignment to Final fields raises an exception"""
        # Create an account with Final fields
        account = Account(
            Id="001XX000003DGTRO",
            Name="Final Test",
            CreatedDate=datetime.datetime(2023, 1, 1, 12, 0, 0).isoformat(),
            LastModifiedDate=datetime.datetime(2023, 1, 1, 12, 0, 0).isoformat(),
        )

        # Attempt to modify a Final field
        with pytest.raises(ReadOnlyAssignmentException):
            account.CreatedDate = datetime.datetime.now()  # type: ignore

        # Regular fields should still be modifiable
        account.Name = "Modified Name"  # This should work fine
        assert account.Name == "Modified Name"
