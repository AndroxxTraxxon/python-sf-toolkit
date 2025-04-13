from sf_toolkit.data.sobject import SObject
from sf_toolkit.data.fields import IdField, TextField

class Product(SObject, api_name="Product2"):
    Id = IdField()
    Name = TextField()
    ExternalId__c = TextField()
    Description = TextField()
