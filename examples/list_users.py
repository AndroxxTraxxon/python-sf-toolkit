from sf_toolkit import SalesforceClient, SObject
from sf_toolkit.auth import cli_login
from sf_toolkit.data.fields import IdField, TextField

class User(SObject):
    Id = IdField()
    Name = TextField()

with SalesforceClient(login=cli_login()):
    for user in User.select().execute().records:
        print(user.Name, user.Id)
