from sf_toolkit.data.fields import (
    DateField,
    DateTimeField,
    FieldFlag,
    IdField,
    IntField,
    NumberField,
    TextField,
)
from sf_toolkit.data.sobject import SObject


class Opportunity(SObject):
    Id = IdField()
    Name = TextField()
    Amount = NumberField()
    CloseDate = DateField()
    StageName = TextField()


class Account(SObject):
    Id = IdField()
    Name = TextField()
    Industry = TextField()
    AnnualRevenue = NumberField()
    NumberOfEmployees = IntField()
    Description = TextField()
    CreatedDate = DateTimeField(FieldFlag.readonly)
    LastModifiedDate = DateTimeField(FieldFlag.readonly)


class Product(SObject, api_name="Product2"):
    Id = IdField()
    Name = TextField()
    ExternalId__c = TextField()
    Description = TextField()


class Contact(SObject):
    Id = IdField()
    FirstName = TextField()
    LastName = TextField()
    Email = TextField()
    Phone = TextField()
    AccountId = IdField()
    Title = TextField()
