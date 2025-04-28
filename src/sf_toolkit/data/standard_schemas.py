from sf_toolkit.client import SalesforceClient
from sf_toolkit.data.fields import IdField
from .sobject import SObject


class User(SObject):
    Id = IdField()

    def password_expired(self, connection: str | SalesforceClient | None = None) -> bool:
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

    def set_password(self, password: str, connection: str | SalesforceClient | None = None):
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
        """Reset the user's password and return the new system-generated """
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
