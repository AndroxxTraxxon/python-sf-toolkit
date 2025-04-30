from .base import ApiResource
from ..client import I_SalesforceClient


class Tooling(ApiResource):
    client: I_SalesforceClient

    def __init__(self, client: I_SalesforceClient | str | None = None):
        if not client or isinstance(client, str):
            self.client = I_SalesforceClient.get_connection(client)
        else:
            self.client = client


    def execute_anonymous(self, code: str):
        return self.client.get(
            self.client.tooling_url + "/executeAnonymous",
            params={"anonymousBody": code}
        ).json()
