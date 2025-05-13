from sf_toolkit.client import SalesforceClient
from sf_toolkit.data.fields import (
    DateTimeField,
    IdField,
    TextField,
    BlobField,
    IntField,
    CheckboxField,
    FieldFlag,
    PicklistField,
)
from .sobject import SObject


class User(SObject):
    Id = IdField()

    def password_expired(
        self, connection: str | SalesforceClient | None = None
    ) -> bool:
        assert self.Id is not None, "User Id must be set to check password expiration"
        if isinstance(connection, str):
            client = SalesforceClient.get_connection(connection)
        elif isinstance(connection, SalesforceClient):
            client = connection
        else:
            client = self._client_connection()

        url = f"{client.sobjects_url}/{self.attributes.type}/{self.Id}/password"
        response = client.get(url, headers={"Accept": "application/json"})
        return response.json()["IsExpired"]

    def set_password(
        self, password: str, connection: str | SalesforceClient | None = None
    ):
        assert self.Id is not None, "User Id must be set to set password"
        if isinstance(connection, str):
            client = SalesforceClient.get_connection(connection)
        elif isinstance(connection, SalesforceClient):
            client = connection
        else:
            client = self._client_connection()

        url = f"{client.sobjects_url}/{self.attributes.type}/{self.Id}/password"
        client.post(url, json={"NewPassword": password})

    def reset_password(self, connection: str | SalesforceClient | None = None):
        """Reset the user's password and return the new system-generated"""
        assert self.Id is not None, "User Id must be set to set password"
        if isinstance(connection, str):
            client = SalesforceClient.get_connection(connection)
        elif isinstance(connection, SalesforceClient):
            client = connection
        else:
            client = self._client_connection()

        url = f"{client.sobjects_url}/{self.attributes.type}/{self.Id}/password"
        response = client.delete(url, headers={"Accept": "application/json"})
        new_password: str = response.json()["NewPassword"]
        return new_password


class ContentVersion(SObject):
    """
    The standard Salesforce ContentVersion object
    https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_contentversion.htm
    """

    Id = IdField()
    ContentDocumentId = IdField()
    ContentLocation = PicklistField(options=["S", "L", "E"])
    Description = TextField()
    PathOnClient = TextField()
    ReasonForChange = TextField()
    Title = TextField()
    VersionData = BlobField()


class Document(SObject):
    """
    The Standard Salesforce Document object
    https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_document.htm
    """

    Id = IdField()
    AuthorId = IdField()
    Name = TextField()
    Body = BlobField()
    BodyLength = IntField(FieldFlag.readonly)
    ContentType = TextField(FieldFlag.readonly)
    Description = TextField()
    DeveloperName = TextField()
    FolderId = IdField()
    IsBodySearchable = CheckboxField()
    IsInternalUserOnly = CheckboxField()
    IsPublic = CheckboxField()
    Keywords = TextField()
    LastReferencedDate = DateTimeField()
    LastViewedDate = DateTimeField()
    Name = TextField()
    NamespacePrefix = TextField()
    Type = TextField()
    Url = TextField()


class Attachment(SObject):
    """
    The Standard Salesforce Attachment object
    https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_attachment.htm
    """

    Id = IdField()
    Body = BlobField()
    BodyLength = IntField(FieldFlag.readonly)
    ContentType = TextField(FieldFlag.readonly)
    Description = TextField()
    IsEncrypted = TextField(FieldFlag.readonly)
    IsPrivate = CheckboxField()
    Name = TextField()
    OwnerId = IdField()
    ParentId = IdField()
