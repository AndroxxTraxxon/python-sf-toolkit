
from types import TracebackType

from .client import SalesforceClient
from .auth import SalesforceAuth, SfSessionId

class Salesforce:

    client: SalesforceClient
    session_id: SfSessionId
    login: SalesforceAuth

    def __init__(
        self,
        login: SalesforceAuth,
        client: SalesforceClient | None,
    ):
        self.login = login
        self.client = client or SalesforceClient()

    def _auth(self):
        self.session_id = self.login()

    def __enter__(self):
        self.client.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        self.client.__exit__(exc_type, exc_value, traceback)

    async def __aenter__(self):
        await self.client.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.client.__aexit__(exc_type, exc_value, traceback)


_connections: dict[str, Salesforce] = {}
