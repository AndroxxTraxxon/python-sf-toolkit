from types import TracebackType

from httpx import Client, AsyncClient

class SalesforceClient:
    _sync: Client
    _async: AsyncClient

    def __init__(self, syncClient: Client | None = None, asyncClient: AsyncClient | None = None):
        self._sync = syncClient or Client()
        self._async = asyncClient or AsyncClient()


    def __enter__(self):
        self._sync.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        self._sync.__exit__(exc_type, exc_value, traceback)

    async def __aenter__(self):
        await self._async.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self._async.__aexit__(exc_type, exc_value, traceback)
