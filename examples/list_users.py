from sf_toolkit import SalesforceClient, SObject
from sf_toolkit.auth import cli_login
from sf_toolkit.data.fields import IdField, TextField, DateTimeField, FieldFlag

class User(SObject):
    Id = IdField()
    Name = TextField(FieldFlag.readonly)
    Department = TextField()
    Username = TextField()
    CreatedDate = DateTimeField(FieldFlag.readonly)

def print_users():
    query = User.query()\
        .where(Name__like='%Integration%')\
        .limit(10)
    result = query.execute()
    for user in result:
        print(
            user.Name, # type eval to str
            user.Id, # type eval to str
            user.Username, # type eval to str
            # field value is automatically parsed into datetime type
            user.CreatedDate.date().isoformat(),
            sep=' | '
        )
        user.Department = "System Automations"

    result.as_list().save()

    print(result.as_list())
    print(len(result), "Total Users")

with SalesforceClient(login=cli_login()) as client:
    print_users()
