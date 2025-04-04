import pytest
from datetime import datetime, timedelta
from sf_toolkit.exceptions import SalesforceError

from ..test_sobject import Opportunity, Account


def test_opportunity_crud(sf_client):
    """Test creating, updating, and deleting an Opportunity"""
    # Generate unique name using timestamp to avoid conflicts
    unique_name = f"Test Opportunity {datetime.now().strftime('%Y%m%d%H%M%S')}"
    close_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    # Create new opportunity
    opp = Opportunity(
        Name=unique_name,
        StageName="Prospecting",
        CloseDate=close_date,
        Amount=10000.00
    )

    opp.save()

    # Verify opportunity was created
    assert hasattr(opp, 'Id')
    assert opp.Id is not None
    assert opp.Name == unique_name
    assert opp.StageName == "Prospecting"

    # Update opportunity
    updated_name = f"{unique_name} - Updated"
    opp.update_values(
        Name=updated_name,
        StageName="Qualification",
        Amount=15000.00
    )
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


def test_reload_after_success_flag(sf_client):
    """Test that reload_after_success flag updates multiple references to the same record"""
    # Create a test account
    unique_name = f"Test Account {datetime.now().strftime('%Y%m%d%H%M%S')}"
    account = Account(
        Name=unique_name,
        Industry="Technology"
    )
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
        account_ref1.save(reload_after_success=True)

        # Verify first reference has updated data
        assert account_ref1.Name == new_name

        # Second reference still has old data since it wasn't reloaded
        assert account_ref2.Name == unique_name

        # Now update second reference with reload_after_success=True
        description = "This is a test description"
        account_ref2.Description = description
        account_ref2.save(reload_after_success=True)

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
