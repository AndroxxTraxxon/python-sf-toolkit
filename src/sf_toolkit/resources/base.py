from ..client import SalesforceClient


class ApiResource:
    client: SalesforceClient

    def __init__(self, client: SalesforceClient | str | None = None):
        if not client or isinstance(client, str):
            self.client = SalesforceClient.get_connection(client)
        else:
            self.client = client
