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
    opp.update(
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
