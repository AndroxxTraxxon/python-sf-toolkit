import pytest
from datetime import datetime, timedelta
from sf_toolkit.exceptions import SalesforceError

from ..unit_test_models import Opportunity, Account, Product


def test_opportunity_crud(sf_client):
    """Test creating, updating, and deleting an Opportunity"""
    # Generate unique name using timestamp to avoid conflicts
    unique_name = f"Test Opportunity {datetime.now().strftime('%Y%m%d%H%M%S')}"
    close_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    # Create new opportunity
    opp = Opportunity(
        Name=unique_name, StageName="Prospecting", CloseDate=close_date, Amount=10000.00
    )

    created_opp_id = None

    try:
        opp.save()
        created_opp_id = opp.Id

        # Verify opportunity was created
        assert hasattr(opp, "Id")
        assert opp.Id is not None
        assert opp.Name == unique_name
        assert opp.StageName == "Prospecting"

        # Update opportunity
        updated_name = f"{unique_name} - Updated"
        opp.update_values(Name=updated_name, StageName="Qualification", Amount=15000.00)
        opp.save()

        # Verify opportunity was updated
        retrieved_opp = Opportunity.read(opp.Id)
        assert retrieved_opp.Name == updated_name
        assert retrieved_opp.StageName == "Qualification"
        assert retrieved_opp.Amount == 15000.00

        # Delete opportunity
        opp.delete(clear_id_field=False)

        # Verify opportunity was deleted
        with pytest.raises(SalesforceError):
            Opportunity.read(opp.Id)

    finally:
        # Ensure cleanup happens even if test fails
        if created_opp_id and hasattr(opp, "Id") and opp.Id is not None:
            try:
                opp.delete(clear_id_field=False)
            except Exception:
                # If deletion fails, we've already tried our best to clean up
                pass


def test_reload_after_success_flag(sf_client):
    """Test that reload_after_success flag updates multiple references to the same record"""
    # Create a test account
    unique_name = f"Test Account {datetime.now().strftime('%Y%m%d%H%M%S')}"
    account = Account(Name=unique_name, Industry="Technology")
    account.save()

    try:
        # Create two references to the same account
        account_ref1 = Account.read(account.Id)
        account_ref2 = Account.read(account.Id)

        # Verify both references have the same data
        assert account_ref1.Name == unique_name
        assert account_ref2.Name == unique_name

        # Update using first reference with reload_after_success=True
        new_name = f"{unique_name} - Updated"
        account_ref1.Name = new_name
        account_ref1.save(reload_after_success=True, only_changes=True)

        # Verify first reference has updated data
        assert account_ref1.Name == new_name

        # Second reference still has old data since it wasn't reloaded
        assert account_ref2.Name == unique_name

        # Now update second reference with reload_after_success=True
        description = "This is a test description"
        account_ref2.Description = description
        account_ref2.save(reload_after_success=True, only_changes=True)

        # Verify second reference now has both updated name and description
        assert account_ref2.Name == new_name
        assert account_ref2.Description == description

        # Read again to confirm changes were actually saved to Salesforce
        account_ref3 = Account.read(account.Id)
        assert account_ref3.Name == new_name
        assert account_ref3.Description == description

    finally:
        # Clean up
        account.delete()


def test_upsert_with_external_id(sf_client):
    """Test upserting a record using an external ID field"""
    # Generate unique name and external ID
    unique_name = f"Ext ID Account {datetime.now().strftime('%Y%m%d%H%M%S')}"
    external_id = f"EXT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Create account with external ID
    product = Product(
        Name=unique_name, ExternalId__c=external_id, Description="Test Description"
    )

    try:
        # First save - should create the record
        product.save(external_id_field="ExternalId__c")

        # Verify the record was created and has an ID
        assert hasattr(product, "Id")
        assert product.Id is not None
        initial_id = product.Id

        # Modify the account
        product.Name = f"{unique_name} - Updated"

        # Save again with external ID - should update the existing record
        product.save()

        # Verify the ID didn't change (same record was updated)
        assert product.Id == initial_id

        # Create new instance with same external ID but different data
        upsert_product = Product(
            Name=f"{unique_name} - Upserted",
            ExternalId__c=external_id,
            Description="Manufacturing",
        )

        # Should update the existing record instead of creating new one
        upsert_product.save(external_id_field="ExternalId__c")

        # Verify it matched and updated the existing record
        assert hasattr(upsert_product, "Id")
        assert upsert_product.Id == initial_id

        # Retrieve to confirm changes
        retrieved = Product.read(initial_id)
        assert retrieved.Name == f"{unique_name} - Upserted"
        assert retrieved.Description == "Manufacturing"

    finally:
        # Clean up
        if hasattr(product, "Id") and product.Id:
            product.delete()


def test_update_only_flag(sf_client):
    """Test that update_only flag prevents creation of new records"""
    # Generate unique name
    unique_name = f"Update Only Test {datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Create account object but don't save it
    account = Account(Name=unique_name, Industry="Technology")

    # Attempt to save with update_only=True should fail
    with pytest.raises(
        ValueError, match="Cannot update record without an ID or external ID"
    ):
        account.save(update_only=True)

    # Now save it normally to create it
    account.save()
    account_id = account.Id

    try:
        # Modify and update with update_only=True should succeed
        account.Name = f"{unique_name} - Updated"
        account.save(update_only=True)

        # Verify update worked
        retrieved = Account.read(account_id)
        assert retrieved.Name == f"{unique_name} - Updated"

        # Create another account with an ID but don't save it
        nonexistent_account = Account(
            Id="001000000000000AAA",  # Non-existent ID
            Name="This should fail",
        )

        # This should fail since the ID doesn't exist
        with pytest.raises(SalesforceError):
            nonexistent_account.save(update_only=True)

    finally:
        # Clean up
        if hasattr(account, "Id") and account.Id:
            account.delete()


def test_only_changes_with_upsert(sf_client):
    """Test that only_changes flag works correctly with upsert operations"""
    # Generate unique data
    unique_name = f"Only Changes Test {datetime.now().strftime('%Y%m%d%H%M%S')}"
    external_id = f"CHG-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Create and save account
    product = Product(
        Name=unique_name, ExternalId__c=external_id, Description="Initial description"
    )
    product.save()

    try:
        # Create a new instance with the same external ID but only change one field
        update_product = Product(
            ExternalId__c=external_id, Description="Updated description"
        )

        update_product.save(
            external_id_field="ExternalId__c", reload_after_success=True
        )

        # Retrieve to confirm changes
        retrieved = Product.read(product.Id)
        assert retrieved.Name == unique_name  # Unchanged
        assert retrieved.Description == "Updated description"  # Changed

        # Now update multiple fields with only_changes
        update_product = Product(
            Name="New Name",
            Description="Updated description",
            ExternalId__c=external_id,
        )
        update_product.save(external_id_field="ExternalId__c")

        # Verify only the modified fields were updated
        retrieved = Product.read(product.Id)
        assert retrieved.Name == "New Name"
        assert retrieved.Description == "Updated description"

    finally:
        # Clean up
        if hasattr(product, "Id") and product.Id:
            product.delete()
