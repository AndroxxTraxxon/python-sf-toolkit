import pytest
import datetime
from time import sleep

from sf_toolkit.data.fields import dirty_fields
from sf_toolkit.data.sf_io import (
    delete,
    read,
    save,
    save_insert,
    save_update,
    save_upsert,
    sobject_list,
)

from ..unit_test_models import Product, Account


def test_insert_and_delete(sf_client):
    """Test inserting and then deleting an SObject"""
    # Create unique name to avoid conflicts
    unique_name = (
        f"Test Insert Account {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create new account
    account = Account(
        Name=unique_name, Industry="Technology", Description="Test insert account"
    )

    try:
        # Directly test save_insert method
        save_insert(account)

        # Verify the account was created and has an ID
        assert hasattr(account, "Id")
        assert account.Id is not None
        assert isinstance(account.Id, str)

        # Retrieve the account to verify it exists
        retrieved = read(Account, account.Id)
        assert retrieved.Name == unique_name
        assert retrieved.Industry == "Technology"
        assert retrieved.Description == "Test insert account"

    finally:
        # Clean up - delete the account if it was created
        if hasattr(account, "Id") and account.Id:
            delete(account)


def test_update(sf_client):
    """Test updating an existing SObject"""
    # Create unique name to avoid conflicts
    unique_name = (
        f"Test Update Account {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create new account first
    account = Account(
        Name=unique_name, Industry="Healthcare", Description="Original description"
    )
    save(account)

    try:
        # Now update the account
        account.Industry = "Financial Services"
        account.Description = "Updated description"
        account.AnnualRevenue = 5000000.0

        # Use save_update to update the account
        save_update(account)

        # Retrieve the account to verify changes
        retrieved = read(Account, account.Id)
        assert retrieved.Name == unique_name  # Unchanged
        assert retrieved.Industry == "Financial Services"  # Changed
        assert retrieved.Description == "Updated description"  # Changed
        assert retrieved.AnnualRevenue == 5000000.0  # Changed

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            delete(account)


def test_only_changes_flag(sf_client):
    """Test that only_changes flag only updates dirty fields"""
    # Create unique name to avoid conflicts
    unique_name = (
        f"Test Only Changes {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create new account with multiple fields
    account = Account(
        Name=unique_name,
        Industry="Retail",
        Description="Original description",
        NumberOfEmployees=500,
    )
    save(account)

    try:
        # Get a fresh copy to manipulate
        account = read(Account, account.Id)

        # Only change one field
        account.Description = "Modified description"

        # Update with only_changes=True (default)
        save_update(account)

        # Retrieve a fresh copy
        retrieved = read(Account, account.Id)
        assert retrieved.Description == "Modified description"

        # Check if the client calls match the expected behavior by making another change
        # and setting a field to None
        retrieved.NumberOfEmployees = None
        retrieved.Industry = "Education"

        # Update again
        save_update(retrieved)

        # Get a final copy to verify
        final = read(Account, account.Id)
        assert final.Industry == "Education"
        assert final.NumberOfEmployees is None

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            delete(account)


def test_save_with_reload(sf_client):
    """Test saving with reload_after_success to see fields updated by triggers"""
    # Create unique name to avoid conflicts
    unique_name = f"Test Reload {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    # Create new account
    account = Account(Name=unique_name, Industry="Construction")

    try:
        # Save with reload_after_success=True
        save(account, reload_after_success=True)

        # Verify system fields were populated (these come from the reload)
        assert hasattr(account, "CreatedDate")
        assert account.CreatedDate is not None
        assert hasattr(account, "LastModifiedDate")
        assert account.LastModifiedDate is not None

        # Now update a field
        original_modified_date = account.LastModifiedDate
        account.Description = "Added after creation"
        sleep(1)

        # Save with reload again
        save(account, reload_after_success=True)

        # Verify LastModifiedDate was updated
        assert account.LastModifiedDate > original_modified_date

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            delete(account)


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
    save(product)

    try:
        # Create a new instance with the same external ID but different data
        updated_product = Product(
            Name="Updated Product Name",  # Changed
            Description="Updated product description",  # Changed
            ExternalId__c=unique_external_id,  # Same external ID
        )

        # Use upsert to update the existing record
        save_upsert(
            updated_product,
            external_id_field="ExternalId__c",
            reload_after_success=True,
        )

        # Verify the record was updated
        assert hasattr(updated_product, "Id")
        assert updated_product.Id == product.Id  # Same record
        assert updated_product.Name == "Updated Product Name"
        assert updated_product.Description == "Updated product description"

        # Retrieve to double-check
        retrieved = read(Product, product.Id)
        assert retrieved.Name == "Updated Product Name"

    finally:
        # Clean up
        if hasattr(product, "Id") and product.Id:
            delete(product)


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
        save_upsert(product, external_id_field="ExternalId__c")

        # Verify the record was created with a new ID
        assert hasattr(product, "Id")
        assert product.Id is not None

        # Retrieve to confirm
        retrieved = read(Product, product.Id)
        assert retrieved.Name == "Test Product"
        assert retrieved.Description == "A test product for upsert"
        assert retrieved.ExternalId__c == unique_external_id

    finally:
        # Clean up
        if hasattr(product, "Id") and product.Id:
            delete(product)


def test_update_only_flag(sf_client):
    """Test that update_only flag prevents creation of new records"""
    # Generate unique name
    unique_name = (
        f"Update Only Test {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create account but don't save it
    account = Account(Name=unique_name, Industry="Technology")

    # Attempt to save with update_only=True should fail
    with pytest.raises(
        ValueError, match="Cannot update record without an ID or external ID"
    ):
        save(account, update_only=True)

    # Now save it normally to create it
    save(account)

    try:
        # Modify and update with update_only=True should succeed
        account.Name = f"{unique_name} - Updated"
        save(account, update_only=True)

        # Verify update worked
        retrieved = read(Account, account.Id)
        assert retrieved.Name == f"{unique_name} - Updated"

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            delete(account)


def test_batch_modify_and_save(sf_client):
    """Test creating multiple records, modifying them, and saving the changes"""
    # Number of records to create
    num_records = 5
    base_name = f"Batch Test {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    # Create accounts
    accounts = []
    for i in range(num_records):
        account = Account(
            Name=f"{base_name} #{i}",
            Industry="Technology",
            Description=f"Initial description #{i}",
        )
        save(account)
        accounts.append(account)

    ids = [account.Id for account in accounts]

    try:
        # Modify all accounts
        for i, account in enumerate(accounts):
            account.Description = f"Updated description #{i}"
            account.Industry = "Healthcare"

        # Save all modifications
        for account in accounts:
            save(account)

        # Retrieve all accounts to verify changes
        retrieved_accounts = sobject_list(Account, *ids)

        # Verify all changes were saved
        for i, account in enumerate(retrieved_accounts):
            assert account.Name == f"{base_name} #{i}"
            assert account.Industry == "Healthcare"
            assert account.Description == f"Updated description #{i}"

    finally:
        # Clean up
        for account in accounts:
            if hasattr(account, "Id") and account.Id:
                delete(account)


def test_dirty_fields_tracking(sf_client):
    """Test that dirty fields are properly tracked and reset after save"""
    # Create unique name
    unique_name = (
        f"Dirty Fields Test {datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )

    # Create account
    account = Account(Name=unique_name, Industry="Consulting")

    # After initialization, no fields should be dirty
    assert dirty_fields(account) is not None
    assert not dirty_fields(account)

    # Save the account
    save(account)

    # After saving, no fields should be dirty
    assert len(dirty_fields(account)) == 0

    try:
        # Modify a field
        account.Description = "New description"

        # Only the modified field should be dirty
        assert len(dirty_fields(account)) == 1
        assert "Description" in dirty_fields(account)

        # Modify another field
        account.Industry = "Education"

        # Both modified fields should be dirty
        assert len(dirty_fields(account)) == 2
        assert "Description" in dirty_fields(account)
        assert "Industry" in dirty_fields(account)

        # Save the changes
        save(account)

        # After saving, no fields should be dirty again
        assert len(dirty_fields(account)) == 0

        # Retrieve the account to verify changes
        retrieved = read(Account, account.Id)
        assert retrieved.Description == "New description"
        assert retrieved.Industry == "Education"

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            delete(account)
