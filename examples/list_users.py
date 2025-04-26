from sf_toolkit import SalesforceClient, SObject
from sf_toolkit.auth import cli_login
from sf_toolkit.data.fields import IdField, TextField

class User(SObject):
    Id = IdField()
    Name = TextField()
    Username = TextField()

with SalesforceClient(login=cli_login()) as client:
    print(client.base_url)
    query = User.query().where(Name__like='%Integration%').limit(10)
    for user in (result:=query.execute()):
        print(user.Name, user.Id, user.Username, sep=' | ')

    print(result.as_list())
    print(len(result), "Total Users")
