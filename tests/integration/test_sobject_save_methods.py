import pytest
import datetime
from time import sleep
from sf_toolkit.data.sobject import SObject
from sf_toolkit.data.fields import (
    FieldFlag,
    IdField,
    NumberField, TextField, IntField, DateTimeField
)

from .models import Product

# Test SObject classes
class _TestAccount(SObject, api_name="Account"):
    Id = IdField()
    Name = TextField()
    Industry = TextField()
    Description = TextField()
    AnnualRevenue = NumberField()
    NumberOfEmployees = IntField()
    CreatedDate = DateTimeField(FieldFlag.readonly)
    LastModifiedDate = DateTimeField(FieldFlag.readonly)


class _TestContact(SObject, api_name="Contact"):
    Id = IdField()
    FirstName = TextField()
    LastName = TextField()
    Email = TextField()
    Phone = TextField()
    AccountId = IdField()
    Title = TextField()
    ExternalId__c = TextField()


def test_insert_and_delete(sf_client):
    """Test inserting and then deleting an SObject"""
    # Create unique name to avoid conflicts
    unique_name = (
        f"Test Insert Account {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create new account
    account = _TestAccount(
        Name=unique_name, Industry="Technology", Description="Test insert account"
    )

    try:
        # Test save_insert method
        account.save_insert()

        # Verify the account was created and has an ID
        assert hasattr(account, "Id")
        assert account.Id is not None
        assert isinstance(account.Id, str)

        # Retrieve the account to verify it exists
        retrieved = _TestAccount.read(account.Id)
        assert retrieved.Name == unique_name
        assert retrieved.Industry == "Technology"
        assert retrieved.Description == "Test insert account"

    finally:
        # Clean up - delete the account if it was created
        if hasattr(account, "Id") and account.Id:
            account.delete()


def test_update(sf_client):
    """Test updating an existing SObject"""
    # Create unique name to avoid conflicts
    unique_name = (
        f"Test Update Account {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create new account first
    account = _TestAccount(
        Name=unique_name, Industry="Healthcare", Description="Original description"
    )
    account.save()

    try:
        # Now update the account
        account.Industry = "Financial Services"
        account.Description = "Updated description"
        account.AnnualRevenue = 5000000.0

        # Use save_update to update the account
        account.save_update()

        # Retrieve the account to verify changes
        retrieved = _TestAccount.read(account.Id)
        assert retrieved.Name == unique_name  # Unchanged
        assert retrieved.Industry == "Financial Services"  # Changed
        assert retrieved.Description == "Updated description"  # Changed
        assert retrieved.AnnualRevenue == 5000000.0  # Changed

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            account.delete()


def test_only_changes_flag(sf_client):
    """Test that only_changes flag only updates dirty fields"""
    # Create unique name to avoid conflicts
    unique_name = (
        f"Test Only Changes {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create new account with multiple fields
    account = _TestAccount(
        Name=unique_name,
        Industry="Retail",
        Description="Original description",
        NumberOfEmployees=500,
    )
    account.save()

    try:
        # Get a fresh copy to manipulate
        account = _TestAccount.read(account.Id)

        # Only change one field
        account.Description = "Modified description"

        # Update with only_changes=True (default)
        account.save_update()

        # Retrieve a fresh copy
        retrieved = _TestAccount.read(account.Id)
        assert retrieved.Description == "Modified description"

        # Check if the client calls match the expected behavior by making another change
        # and setting a field to None
        retrieved.NumberOfEmployees = None
        retrieved.Industry = "Education"

        # Update again
        retrieved.save_update()

        # Get a final copy to verify
        final = _TestAccount.read(account.Id)
        assert final.Industry == "Education"
        assert final.NumberOfEmployees is None

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            account.delete()


def test_save_with_reload(sf_client):
    """Test saving with reload_after_success to see fields updated by triggers"""
    # Create unique name to avoid conflicts
    unique_name = f"Test Reload {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    # Create new account
    account = _TestAccount(Name=unique_name, Industry="Construction")

    try:
        # Save with reload_after_success=True
        account.save(reload_after_success=True)

        # Verify system fields were populated (these come from the reload)
        assert hasattr(account, "CreatedDate")
        assert account.CreatedDate is not None
        assert hasattr(account, "LastModifiedDate")
        assert account.LastModifiedDate is not None

        # Now update a field
        original_modified_date = account.LastModifiedDate
        account.Description = "Added after creation"
        sleep(0.5)

        # Save with reload again
        account.save(reload_after_success=True)

        # Verify LastModifiedDate was updated
        assert account.LastModifiedDate > original_modified_date

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            account.delete()


def test_upsert_existing(sf_client):
    """Test upserting an existing record using an external ID"""
    # Generate unique external ID
    unique_external_id = f"EXT-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    # Create a product with the external ID
    product = Product(
        Name="Test Product",
        Description="Original product description",
        ExternalId__c=unique_external_id,
    )
    product.save()

    try:
        # Create a new instance with the same external ID but different data
        updated_product = Product(
            Name="Updated Product Name",  # Changed
            Description="Updated product description",  # Changed
            ExternalId__c=unique_external_id,  # Same external ID
        )

        # Use upsert to update the existing record
        updated_product.save_upsert(
            external_id_field="ExternalId__c", reload_after_success=True
        )

        # Verify the record was updated
        assert hasattr(updated_product, "Id")
        assert updated_product.Id == product.Id  # Same record
        assert updated_product.Name == "Updated Product Name"
        assert updated_product.Description == "Updated product description"

        # Retrieve to double-check
        retrieved = Product.read(product.Id)
        assert retrieved.Name == "Updated Product Name"

    finally:
        # Clean up
        if hasattr(product, "Id") and product.Id:
            product.delete()


def test_upsert_new(sf_client):
    """Test upserting a new record using an external ID"""
    # Generate unique external ID
    unique_external_id = f"EXT-NEW-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    # Create a product with the external ID but don't save it first
    product = Product(
        Name="Test Product",
        Description="A test product for upsert",
        ExternalId__c=unique_external_id,
    )

    try:
        # Use upsert to create a new record
        product.save_upsert(external_id_field="ExternalId__c")

        # Verify the record was created with a new ID
        assert hasattr(product, "Id")
        assert product.Id is not None

        # Retrieve to confirm
        retrieved = Product.read(product.Id)
        assert retrieved.Name == "Test Product"
        assert retrieved.Description == "A test product for upsert"
        assert retrieved.ExternalId__c == unique_external_id

    finally:
        # Clean up
        if hasattr(product, "Id") and product.Id:
            product.delete()


def test_update_only_flag(sf_client):
    """Test that update_only flag prevents creation of new records"""
    # Generate unique name
    unique_name = (
        f"Update Only Test {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create account but don't save it
    account = _TestAccount(Name=unique_name, Industry="Technology")

    # Attempt to save with update_only=True should fail
    with pytest.raises(
        ValueError, match="Cannot update record without an ID or external ID"
    ):
        account.save(update_only=True)

    # Now save it normally to create it
    account.save()

    try:
        # Modify and update with update_only=True should succeed
        account.Name = f"{unique_name} - Updated"
        account.save(update_only=True)

        # Verify update worked
        retrieved = _TestAccount.read(account.Id)
        assert retrieved.Name == f"{unique_name} - Updated"

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            account.delete()


def test_batch_modify_and_save(sf_client):
    """Test creating multiple records, modifying them, and saving the changes"""
    # Number of records to create
    num_records = 5
    base_name = f"Batch Test {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    # Create accounts
    accounts = []
    for i in range(num_records):
        account = _TestAccount(
            Name=f"{base_name} #{i}",
            Industry="Technology",
            Description=f"Initial description #{i}",
        )
        account.save()
        accounts.append(account)

    ids = [account.Id for account in accounts]

    try:
        # Modify all accounts
        for i, account in enumerate(accounts):
            account.Description = f"Updated description #{i}"
            account.Industry = "Healthcare"

        # Save all modifications
        for account in accounts:
            account.save()

        # Retrieve all accounts to verify changes
        retrieved_accounts = _TestAccount.list(*ids)

        # Verify all changes were saved
        for i, account in enumerate(retrieved_accounts):
            assert account.Name == f"{base_name} #{i}"
            assert account.Industry == "Healthcare"
            assert account.Description == f"Updated description #{i}"

    finally:
        # Clean up
        for account in accounts:
            if hasattr(account, "Id") and account.Id:
                account.delete()


def test_dirty_fields_tracking(sf_client):
    """Test that dirty fields are properly tracked and reset after save"""
    # Create unique name
    unique_name = (
        f"Dirty Fields Test {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create account
    account = _TestAccount(Name=unique_name, Industry="Consulting")

    # After initialization, no fields should be dirty
    assert hasattr(account, "dirty_fields")
    assert account.dirty_fields is not None
    assert not account.dirty_fields

    # Save the account
    account.save()

    # After saving, no fields should be dirty
    assert len(account._dirty_fields) == 0

    try:
        # Modify a field
        account.Description = "New description"

        # Only the modified field should be dirty
        assert len(account._dirty_fields) == 1
        assert "Description" in account._dirty_fields

        # Modify another field
        account.Industry = "Education"

        # Both modified fields should be dirty
        assert len(account._dirty_fields) == 2
        assert "Description" in account._dirty_fields
        assert "Industry" in account._dirty_fields

        # Save the changes
        account.save()

        # After saving, no fields should be dirty again
        assert len(account._dirty_fields) == 0

        # Retrieve the account to verify changes
        retrieved = _TestAccount.read(account.Id)
        assert retrieved.Description == "New description"
        assert retrieved.Industry == "Education"

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            account.delete()
