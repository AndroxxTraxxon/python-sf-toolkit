from ..client import I_SalesforceClient


class ApiResource:
    client: I_SalesforceClient

    def __init__(self, client: I_SalesforceClient | str | None = None):
        if not client or isinstance(client, str):
            self.client = I_SalesforceClient.get_connection(client)
        else:
            self.client = client
