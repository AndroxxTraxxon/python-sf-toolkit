"""This file demonstrates how to use the sf_toolkit library to build nested queries.

In this example, we will build a nested query that retrieves information about accounts, their contacts, assets, work orders, and work order line items.
This query originates from the Salesforce API documentation:
    https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/sforce_api_calls_soql_relationships_query_using.htm#sforce_api_calls_soql_relationships_query_using

SELECT Name,
    (SELECT LastName,
        (SELECT AssetLevel,
            (SELECT Description,
                (SELECT LineItemNumber FROM WorkOrderLineItems)
            FROM WorkOrders)
        FROM Assets)
    FROM Contacts)
FROM Account
"""

from sf_toolkit import SalesforceClient, lazy_login, SObject
from sf_toolkit.data.fields import IntField, ListField, TextField


# Define SObject schema types using library
class WorkOrderLineItem(SObject):
    LineItemNumber = TextField()

class WorkOrder(SObject):
    Description = TextField()
    WorkOrderLineItems = ListField(WorkOrderLineItem)

class Asset(SObject):
    AssetLevel = IntField()
    WorkOrders = ListField(WorkOrder)

class Contact(SObject):
    LastName = TextField()
    Assets = ListField(Asset)

class Account(SObject):
    Name = TextField()
    Contacts = ListField(Contact)


with SalesforceClient(login=lazy_login(sf_cli_alias=True)):
    # The query object will be automatically converted to SOQL syntax
    query = Account.query().where(Id__in="SELECT AccountId FROM Contact")
    print(query)

    results = query.execute()
    for record in results:
        print(record.Name, [contact.LastName for contact in record.Contacts], sep=' | ')
