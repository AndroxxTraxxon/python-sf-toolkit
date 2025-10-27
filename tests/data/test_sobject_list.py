from unittest.mock import MagicMock, Mock, AsyncMock
import pytest
import pytest_asyncio

from sf_toolkit.data.transformers import chunked

from sf_toolkit.data.sobject import SObject, SObjectList
from sf_toolkit.data.fields import IdField, TextField, NumberField, dirty_fields
from sf_toolkit.client import SalesforceClient
from sf_toolkit._models import SObjectSaveResult
from sf_toolkit.io import api


# Create test SObject classes
class _TestAccount(SObject, api_name="TestAccount"):
    Id = IdField()
    Name = TextField()
    Industry = TextField()
    Revenue = NumberField()
    ExternalId__c = TextField()


class _TestContact(SObject, api_name="TestContact"):
    Id = IdField()
    FirstName = TextField()
    LastName = TextField()
    Email = TextField()
    AccountId = IdField()
    ExternalId__c = TextField()


@pytest.fixture()
def mock_sf_client():
    """Create a mock SalesforceClient for testing"""
    mock_client = MagicMock(spec=SalesforceClient)
    mock_client.sobjects_url = "/services/data/v57.0/sobjects"
    mock_client.data_url = "/services/data/v57.0/query"
    mock_client.composite_sobjects_url = MagicMock(
        return_value="/services/data/v57.0/composite/sobjects"
    )

    # Mock the async client property
    mock_async_client = Mock()
    mock_client.as_async = mock_async_client
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock(return_value=None)

    # Keep a reference to the original _connections dictionary to restore later
    original_connections = SalesforceClient._connections

    # Add the mock client to the _connections dictionary directly
    SalesforceClient._connections = {
        SalesforceClient.DEFAULT_CONNECTION_NAME: mock_client
    }

    yield mock_client

    # Restore the original _connections dictionary
    SalesforceClient._connections = original_connections


@pytest.fixture
def test_accounts():
    """Create test account objects for testing"""
    accounts = [
        _TestAccount(
            Name=f"Test Account {i}", Industry="Technology", Revenue=1000000.0 * i
        )
        for i in range(1, 6)  # Create 5 accounts
    ]
    return accounts


@pytest.fixture
def test_contacts():
    """Create test contact objects for testing"""
    contacts = [
        _TestContact(
            FirstName=f"First{i}",
            LastName=f"Last{i}",
            Email=f"contact{i}@example.com",
            AccountId=f"001XX0000{i}YYZZZAAA",  # Valid 18-character ID
        )
        for i in range(1, 4)  # Create 3 contacts
    ]
    return contacts


@pytest.fixture
def test_accounts_with_ids(test_accounts):
    """Create test account objects with IDs"""
    for i, account in enumerate(test_accounts):
        account.Id = f"001XX000{i}ABCDEFGHI"  # Valid 18-character ID
        # Clear dirty fields from initialization and ID setting
        dirty_fields(account).clear()
    return test_accounts


def test_sobject_list_init():
    """Test initializing an SObjectList with different inputs"""
    # Test with empty list
    empty_list = SObjectList()
    assert len(empty_list) == 0

    # Test with a list of SObjects
    accounts = [_TestAccount(Name="Test 1"), _TestAccount(Name="Test 2")]
    account_list = SObjectList(accounts)
    assert len(account_list) == 2

    # Test with connection parameter
    connection_list = SObjectList(connection="test_connection")
    assert connection_list.connection == "test_connection"

    # Test with non-SObject objects should raise TypeError
    with pytest.raises(TypeError):
        _ = SObjectList(["not an SObject"])  # pyright: ignore[reportArgumentType]


def test_sobject_list_append_extend():
    """Test append and extend methods"""
    sobject_list = SObjectList()

    # Test append
    account = _TestAccount(Name="Test Account")
    sobject_list.append(account)
    assert len(sobject_list) == 1
    assert sobject_list[0] is account

    # Test append with non-SObject
    with pytest.raises(TypeError):
        sobject_list.append("not an SObject")

    # Test extend
    more_accounts = [_TestAccount(Name="Test 2"), _TestAccount(Name="Test 3")]
    sobject_list.extend(more_accounts)
    assert len(sobject_list) == 3

    # Test extend with non-SObject list
    with pytest.raises(TypeError):
        sobject_list.extend(["not an SObject"])


def test_ensure_consistent_sobject_type(test_accounts, test_contacts):
    """Test _ensure_consistent_sobject_type method"""
    # Test with empty list
    empty_list = SObjectList()
    assert api._ensure_consistent_sobject_type(empty_list) is None

    # Test with single type
    account_list = SObjectList(test_accounts)
    assert api._ensure_consistent_sobject_type(account_list) is _TestAccount

    # Test with mixed types
    mixed_list = SObjectList([test_accounts[0]])
    mixed_list.append(test_contacts[0])
    with pytest.raises(TypeError, match="All objects must be of the same type"):
        api._ensure_consistent_sobject_type(mixed_list)


def test_generate_record_batches(test_accounts):
    """Test _generate_record_batches method"""
    account_list = SObjectList(test_accounts)

    # Basic batching
    batches, emitted_records = api._generate_record_batches(
        account_list, max_batch_size=2
    )
    assert len(batches) == 3  # 5 accounts, batch size 2 = 3 batches
    assert len(batches[0][0]) == 2
    assert len(batches[1][0]) == 2
    assert len(batches[2][0]) == 1

    # Validate structure of a record in the batch
    batch_records, _ = batches[0]
    first_record = batch_records[0]
    assert "attributes" in first_record
    assert first_record["attributes"]["type"] == "TestAccount"
    assert "Name" in first_record

    # Test with only_changes=True
    for account in test_accounts:
        dirty_fields(account).clear()

    # Set a dirty field on one account
    test_accounts[0].Name = "Updated Name"

    # Generate batches with only_changes=True
    batches, emitted_records = api._generate_record_batches(
        account_list, only_changes=True
    )
    assert len(batches) == 1  # Only one record has changes
    assert len(emitted_records) == 1
    records, _ = batches[0]
    assert records[0]["Name"] == "Updated Name"

    # Test with multiple object types - Salesforce processes in chunks by SObject type
    mixed_list = SObjectList([])

    # Create a list with alternating chunks of record types (accounts, contacts, accounts...)
    for i in range(5):  # Create fewer than 10 chunks to verify batch count
        mixed_list.extend(
            [_TestAccount(Name=f"Account A{i}"), _TestAccount(Name=f"Account B{i}")]
        )
        mixed_list.extend(
            [
                _TestContact(FirstName=f"First {i}", LastName="Contact"),
                _TestContact(FirstName=f"Second {i}", LastName="Contact"),
            ]
        )

    # Should create a single batch for all records, as there are fewer than 10 chunks
    batches, emitted_records = api._generate_record_batches(mixed_list)
    # With how the batching works, there should be no separate batches since there are fewer than 10 chunks
    assert len(batches) == 1
    assert len(emitted_records) == 20

    mixed_list.extend(
        [_TestAccount(Name="Account A6"), _TestAccount(Name="Account B6")]
    )
    batches, emitted_records = api._generate_record_batches(mixed_list)

    # First batch should be TestAccounts, second should be TestContact
    assert len(batches[0][0]) == 20
    assert len(batches[1][0]) == 2
    assert len(emitted_records) == 22


def test_save_insert(mock_sf_client, test_accounts):
    """Test save_insert method"""
    account_list = SObjectList(test_accounts)

    # Mock the response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": f"001XX000{i}ABCDEFGHI", "success": True, "errors": []}
        for i, _ in enumerate(test_accounts)
    ]
    mock_sf_client.post.return_value = mock_response

    # Call save_insert
    results = api.save_insert_list(account_list)

    # Verify the API call
    mock_sf_client.post.assert_called_once()
    args, kwargs = mock_sf_client.post.call_args
    assert args[0] == "/services/data/v57.0/composite/sobjects"

    # Verify the results
    assert len(results) == len(test_accounts)
    for result in results:
        assert isinstance(result, SObjectSaveResult)
        assert result.success
        assert not result.errors


def test_save_insert_with_errors(mock_sf_client, test_accounts):
    """Test save_insert with error responses"""
    account_list = SObjectList(test_accounts[:2])

    # Mock error response
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            "id": None,
            "success": False,
            "errors": [
                {
                    "statusCode": "REQUIRED_FIELD_MISSING",
                    "message": "Required field missing",
                    "fields": ["Industry"],
                }
            ],
        },
        {"id": "001XX0000ABCDEFGHI", "success": True, "errors": []},
    ]
    mock_sf_client.post.return_value = mock_response

    # Call save_insert
    results = api.save_insert_list(account_list)

    # Verify results
    assert len(results) == 2
    assert not results[0].success
    assert len(results[0].errors) == 1
    assert results[0].errors[0].statusCode == "REQUIRED_FIELD_MISSING"
    assert results[1].success


def test_save_insert_with_id_error(test_accounts_with_ids, mock_sf_client):
    """Test save_insert with records that already have IDs"""
    account_list = SObjectList(test_accounts_with_ids)

    # Should raise ValueError
    with pytest.raises(
        ValueError, match="Cannot insert record that already has an Id set"
    ):
        api.save_insert_list(account_list)


@pytest.mark.asyncio
async def test_save_insert_async(mock_sf_client, test_accounts):
    """Test save_insert with async execution"""
    # Create enough accounts to trigger async execution
    many_accounts = [_TestAccount(Name=f"Account {i}") for i in range(20)]
    account_list = SObjectList(many_accounts)

    # Mock response for async client
    async_client = mock_sf_client.as_async
    mock_response = AsyncMock()
    mock_response.return_value = Mock()
    mock_response.return_value.json.side_effect = list(
        chunked(
            (
                {"id": f"001XX000{i}ABCDEFGHI", "success": True, "errors": []}
                for i in range(len(many_accounts))
            ),
            5,
        )
    )
    async_client.post = mock_response

    # Call save_insert with concurrency > 1
    results = await api.save_insert_list_async(
        account_list, concurrency=2, batch_size=5
    )

    # Verify async client was used
    async_client.post.assert_called()

    # Verify the results
    assert len(results) == len(many_accounts)
    for i, result in enumerate(results):
        assert result.id == f"001XX000{i}ABCDEFGHI"
        assert result.success
        assert not result.errors


def test_save_update(mock_sf_client, test_accounts_with_ids):
    """Test save_update method"""
    account_list = SObjectList(test_accounts_with_ids)

    # Make changes to the accounts
    for i, account in enumerate(account_list):
        account.Name = f"Updated Account {i}"

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": account.Id, "success": True, "errors": []} for account in account_list
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save_update
    results = api.save_update_list(account_list)

    # Verify API call
    mock_sf_client.patch.assert_called_once()
    args, kwargs = mock_sf_client.patch.call_args
    assert args[0] == "/services/data/v57.0/composite/sobjects"

    # Check if dirty fields were cleared
    for account in account_list:
        assert not dirty_fields(account), "Dirty fields were not cleared after update"

    # Verify results
    assert len(results) == len(account_list)
    for result in results:
        assert result.success


def test_save_update_only_changes(mock_sf_client, test_accounts_with_ids):
    """Test save_update with only_changes=True"""
    account_list = SObjectList(test_accounts_with_ids)
    for account in account_list:
        dirty_fields(account).clear()

    # Make changes to only some fields
    account_list[0].Name = "Updated Name 1"
    account_list[1].Industry = "Healthcare"

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": account.Id, "success": True, "errors": []}
        for account in account_list[:2]  # Only first two have changes
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save_update with only_changes=True
    api.save_update_list(account_list, only_changes=True)

    # Verify API call
    mock_sf_client.patch.assert_called_once()

    # Check the payload
    args, kwargs = mock_sf_client.patch.call_args
    request_data = kwargs.get("json", [])

    # Should include only the two modified records
    assert len(request_data["records"]) == 2

    # First record should have only Name field
    assert "Name" in request_data["records"][0]
    assert "Industry" not in request_data["records"][0]

    # Second record should have only Industry field
    assert "Industry" in request_data["records"][1]
    assert "Name" not in request_data["records"][1]


def test_save_update_no_id(test_accounts, mock_sf_client):
    """Test save_update with records that don't have IDs"""
    account_list = SObjectList(test_accounts)
    account_list.connection = SalesforceClient.DEFAULT_CONNECTION_NAME

    # Should raise ValueError
    with pytest.raises(ValueError, match="Record at index 0 has no Id for update"):
        api.save_update_list(account_list)


@pytest.mark.asyncio
async def test_save_update_async(mock_sf_client, test_accounts_with_ids):
    """Test save_update with async execution"""
    # Create list with accounts
    account_list = SObjectList(test_accounts_with_ids)

    # Make changes
    for account in account_list:
        account.Industry = "Updated Industry"

    # Set up mock for async execution
    async_client = mock_sf_client.as_async.__aenter__.return_value
    async_client.post = AsyncMock()

    # Set up mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": account.Id, "success": True, "errors": []} for account in account_list
    ]
    async_client.post.return_value = mock_response

    # Call save_update with concurrency > 1
    results = await api.save_update_list_async(account_list, concurrency=2)

    # Verify async client's post method was called
    async_client.post.assert_called()

    # Verify results
    assert len(results) == len(account_list)
    for result in results:
        assert result.success


def test_save_upsert(mock_sf_client):
    """Test save_upsert method"""
    # Create list with objects that have external IDs

    object_list = SObjectList(
        [
            _TestAccount(
                Name=f"Account {i}", Industry="Technology", ExternalId__c=f"EXT-{i}"
            )
            for i in range(3)
        ],
        connection=SalesforceClient.DEFAULT_CONNECTION_NAME,
    )

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": f"001XX000{i}ABCDEFGHI", "success": True, "errors": []}
        for i in range(len(object_list))
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save_upsert
    api.save_upsert_list(object_list, external_id_field="ExternalId__c")

    # Verify API call
    mock_sf_client.patch.assert_called()
    args, kwargs = mock_sf_client.patch.call_args
    assert "ExternalId__c" in args[0]  # URL should include external ID field

    # Verify the results were transformed into SObjectSaveResult objects
    results = api.save_upsert_list(object_list, external_id_field="ExternalId__c")
    assert len(results) == len(object_list)
    for result in results:
        assert isinstance(result, SObjectSaveResult)
        assert result.success
        assert result.id is not None
        assert result.id.startswith("001XX000")
        assert not result.errors


def test_save_upsert_missing_external_id(mock_sf_client):
    """Test save_upsert with objects missing external ID"""
    # Create list with objects, one missing external ID
    custom_objects = [
        _TestAccount(Name="Account 1", ExternalId__c="EXT-1"),
        _TestAccount(Name="Account 2"),  # Missing external ID
    ]
    object_list = SObjectList(custom_objects)
    object_list.connection = SalesforceClient.DEFAULT_CONNECTION_NAME

    # Should raise AssertionError
    with pytest.raises(
        AssertionError, match="Record at index 1 has no value for external ID field"
    ):
        api.save_upsert_list(object_list, external_id_field="ExternalId__c")


def test_save_upsert_async(mock_sf_client):
    """Test save_upsert with async execution"""
    # Create objects with external IDs
    custom_objects = [
        _TestAccount(Name=f"Account {i}", ExternalId__c=f"EXT-{i}") for i in range(10)
    ]
    object_list = SObjectList(custom_objects)
    object_list.connection = SalesforceClient.DEFAULT_CONNECTION_NAME

    # Set up mock for async client
    async_client = mock_sf_client.as_async.__aenter__.return_value
    async_client.patch = AsyncMock()
    async_client.patch.return_value = Mock()
    async_client.patch.return_value.json.side_effect = list(
        chunked(
            [
                {"id": f"001XX000{i}ABCDEFGHI", "success": True, "errors": []}
                for i in range(len(custom_objects))
            ],
            2,
        )
    )

    # Call save_upsert with concurrency > 1
    results = api.save_upsert_list(
        object_list, external_id_field="ExternalId__c", concurrency=3, batch_size=2
    )

    # Verify async client was used
    async_client.patch.assert_called()

    # Verify the results
    assert len(results) == len(custom_objects)
    for i, result in enumerate(results):
        assert result.id == f"001XX000{i}ABCDEFGHI"
        assert result.success
        assert not result.errors


def test_save_upsert_only_changes(mock_sf_client):
    """Test save_upsert with only_changes=True"""
    # Create objects with external IDs and set them as not dirty
    custom_objects = [
        _TestAccount(
            Name=f"Account {i}", Industry="Technology", ExternalId__c=f"EXT-{i}"
        )
        for i in range(3)
    ]
    for obj in custom_objects:
        dirty_fields(obj).clear()

    # Make changes to specific fields
    custom_objects[0].Name = "Updated Name"
    custom_objects[1].Industry = "Healthcare"

    object_list = SObjectList(custom_objects)
    object_list.connection = SalesforceClient.DEFAULT_CONNECTION_NAME

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": f"001XX000{i}ABCDEFGHI", "success": True, "errors": []}
        for i in range(2)  # Only 2 objects have changes
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save_upsert with only_changes=True
    api.save_upsert_list(
        object_list, external_id_field="ExternalId__c", only_changes=True
    )

    # Verify API call
    mock_sf_client.patch.assert_called_once()

    # Check the payload in the request
    args, kwargs = mock_sf_client.patch.call_args
    composite_request = kwargs.get("json", {}).get("records", [])

    # Should only send the changed fields
    assert len(composite_request) == 2
    assert "Name" in composite_request[0] and "Industry" not in composite_request[0]
    assert "Industry" in composite_request[1] and "Name" not in composite_request[1]


def test_consistent_sobject_type_for_upsert(mock_sf_client):
    """Test that save_upsert validates consistent SObject types"""
    # Create mixed list
    mixed_list = SObjectList(
        [
            _TestAccount(Name="Account", ExternalId__c="EXT-1"),
            _TestContact(FirstName="First", LastName="Last", ExternalId__c="EXT-2"),
        ]
    )

    # Should raise TypeError
    with pytest.raises(TypeError, match="All objects must be of the same type"):
        api.save_upsert_list(mixed_list, external_id_field="ExternalId__c")


def test_delete(mock_sf_client, test_accounts_with_ids):
    """Test delete method"""
    account_list = SObjectList(test_accounts_with_ids)

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": account.Id, "success": True, "errors": []} for account in account_list
    ]
    mock_sf_client.delete.return_value = mock_response

    # Call delete
    api.delete_list(account_list)

    # Verify API call
    mock_sf_client.delete.assert_called_once()
    args, kwargs = mock_sf_client.delete.call_args
    assert args[0] == "/services/data/v57.0/composite/sobjects"

    # Check IDs are included in params
    ids_param = kwargs.get("params", {}).get("ids", "")
    assert all(account.Id in ids_param for account in account_list)


def test_delete_with_clear_id(mock_sf_client, test_accounts_with_ids):
    """Test delete with clear_id_field=True"""
    account_list = SObjectList(test_accounts_with_ids)

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": account.Id, "success": True, "errors": []} for account in account_list
    ]
    mock_sf_client.delete.return_value = mock_response

    # Call delete with clear_id_field=True
    api.delete_list(account_list, clear_id_field=True)

    # Verify ID fields were cleared
    for account in account_list:
        assert account.Id is None


def test_delete_async(mock_sf_client, test_accounts_with_ids):
    """Test delete with async execution"""
    account_list = SObjectList(test_accounts_with_ids)

    # Set up mock for async client
    async_client = mock_sf_client.as_async.__aenter__.return_value
    mock_response = AsyncMock()
    mock_response.return_value = Mock()
    mock_response.return_value.json.return_value = [
        {"id": account.Id, "success": True, "errors": []} for account in account_list
    ]
    async_client.delete = mock_response

    # Call delete with concurrency > 1
    api.delete_list(account_list, concurrency=2, batch_size=(len(account_list) // 2))

    # Verify async client's delete method was called
    async_client.delete.assert_called()


def test_empty_list_operations(mock_sf_client):
    """Test operations on empty lists"""
    empty_list = SObjectList()

    # All operations should return empty lists without making API calls
    assert api.save_insert_list(empty_list) == []
    assert api.save_update_list(empty_list) == []
    assert api.delete_list(empty_list) == []

    # Verify no API calls were made
    mock_sf_client.post.assert_not_called()
    mock_sf_client.delete.assert_not_called()


def test_save_basic_functionality(mock_sf_client, test_accounts):
    """Test save method with new records (insert case)"""
    account_list = SObjectList(test_accounts)

    # Mock response for insert
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": f"001XX000{i}ABCDEFGHI", "success": True, "errors": []}
        for i, _ in enumerate(test_accounts)
    ]
    mock_sf_client.post.return_value = mock_response

    # Call save
    api.save_list(account_list)

    # Verify API call for insert
    mock_sf_client.post.assert_called_once()
    args, kwargs = mock_sf_client.post.call_args
    assert args[0] == "/services/data/v57.0/composite/sobjects"

    # Verify IDs were set on the records
    for i, account in enumerate(account_list):
        assert account.Id == f"001XX000{i}ABCDEFGHI"


def test_save_update_existing_records(mock_sf_client, test_accounts_with_ids):
    """Test save method with existing records (update case)"""
    account_list = SObjectList(test_accounts_with_ids)

    # Make changes to the accounts
    for i, account in enumerate(account_list):
        account.Name = f"Updated Account {i}"

    # Mock response for update
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": account.Id, "success": True, "errors": []} for account in account_list
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save
    api.save_list(account_list)

    # Verify API call for update
    mock_sf_client.patch.assert_called_once()
    args, kwargs = mock_sf_client.patch.call_args
    assert args[0] == "/services/data/v57.0/composite/sobjects"

    # Check that dirty fields were cleared
    for account in account_list:
        assert not dirty_fields(account)


def test_save_upsert_with_external_id(mock_sf_client):
    """Test save method with external ID field (upsert case)"""
    # Create objects with external IDs
    custom_objects = [
        _TestAccount(Name=f"Account {i}", ExternalId__c=f"EXT-{i}") for i in range(3)
    ]
    object_list = SObjectList(
        custom_objects, connection=SalesforceClient.DEFAULT_CONNECTION_NAME
    )

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": f"001XX000{i}ABCDEFGHI", "success": True, "errors": []}
        for i in range(len(custom_objects))
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save with external_id_field
    api.save_list(object_list, external_id_field="ExternalId__c")

    # Verify API call for upsert
    mock_sf_client.patch.assert_called_once()
    args, kwargs = mock_sf_client.patch.call_args
    assert "ExternalId__c" in args[0]  # URL should include external ID field


def test_save_with_only_changes_option(mock_sf_client, test_accounts_with_ids):
    """Test save method with only_changes=True option"""
    account_list = SObjectList(test_accounts_with_ids)

    # Clear dirty fields from initialization
    for account in account_list:
        dirty_fields(account).clear()

    # Make changes to only some fields
    account_list[0].Name = "Updated Name 1"
    account_list[1].Industry = "Healthcare"

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": account.Id, "success": True, "errors": []}
        for account in account_list[:2]  # Only first two have changes
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save with only_changes=True
    api.save_list(account_list, only_changes=True)

    # Verify API call
    mock_sf_client.patch.assert_called_once()

    # Check the payload contains only changed fields
    args, kwargs = mock_sf_client.patch.call_args
    request_data = kwargs.get("json", [])

    # First record should have only Name field
    assert "Name" in request_data["records"][0]
    assert "Industry" not in request_data["records"][0]

    # Second record should have only Industry field
    assert "Industry" in request_data["records"][1]
    assert "Name" not in request_data["records"][1]


def test_save_with_update_only_option(mock_sf_client):
    """Test save method with update_only=True option"""
    # Create objects with external IDs
    custom_objects = [
        _TestAccount(Name=f"Account {i}", ExternalId__c=f"EXT-{i}") for i in range(2)
    ]
    object_list = SObjectList(
        custom_objects, connection=SalesforceClient.DEFAULT_CONNECTION_NAME
    )

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": f"001XX000{i}ABCDEFGHI", "success": True, "errors": []}
        for i in range(len(custom_objects))
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save with update_only=True
    api.save_list(object_list, external_id_field="ExternalId__c", update_only=True)

    # Verify API call for upsert with update_only
    mock_sf_client.patch.assert_called_once()
    args, kwargs = mock_sf_client.patch.call_args
    assert kwargs.get("json", {}).get("allOrNone") is False  # default is False


def test_save_with_multiple_options(mock_sf_client, test_accounts_with_ids):
    """Test save method with multiple options combined"""
    account_list = SObjectList(test_accounts_with_ids[:2])

    # Clear dirty fields
    for account in account_list:
        dirty_fields(account).clear()

    # Make changes to simulate dirty fields
    account_list[0].Name = "Updated with Multiple Options"

    # Mock response
    mock_response = Mock()
    mock_response.json.return_value = [
        {"id": account_list[0].Id, "success": True, "errors": []}
    ]
    mock_sf_client.patch.return_value = mock_response

    # Call save with multiple options
    api.save_list(account_list, only_changes=True, reload_after_success=False)

    # Verify API call
    mock_sf_client.patch.assert_called_once()

    # Check that only one record was sent (the one with changes)
    args, kwargs = mock_sf_client.patch.call_args
    request_data = kwargs.get("json", [])
    assert len(request_data["records"]) == 1
    assert request_data["records"][0]["Name"] == "Updated with Multiple Options"


def test_save_error_on_update_only_without_id_or_external_id(
    mock_sf_client, test_accounts
):
    """Test save with update_only=True but no ID or external ID field"""
    account_list = SObjectList(test_accounts)

    # Call save with update_only=True but no ID or external ID
    with pytest.raises(
        ValueError,
        match="Cannot perform update_only operation when no records have IDs",
    ):
        api.save_list(account_list, update_only=True)
