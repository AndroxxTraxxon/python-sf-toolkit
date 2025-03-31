from typing import Protocol, Any


class SalesforceClientProtocol(Protocol):
    """Protocol defining the interface of SalesforceClient for typing purposes."""
    base_url: str
    as_async: Any
    api_version: float
    api_usage: Any

    def request(self, method: str, url: Any, resource_name: str = "", **kwargs) -> Any:
        ...

    def get(self, url: str, **kwargs) -> Any:
        ...

    def post(self, url: str, **kwargs) -> Any:
        ...

    @classmethod
    def get_connection(cls, name: str) -> "SalesforceClientProtocol":
        ...

    @property
    def data_url(self) -> str:
        ...

    @property
    def sobjects_url(self) -> str:
        ...

    def composite_sobjects_url(self, sobject: str | None = None) -> str:
        ...

    def __enter__(self) -> "SalesforceClientProtocol":
        ...

    def __exit__(self, exc_type: Any = None, exc_value: Any = None, traceback: Any = None) -> None:
        ...


class AsyncSalesforceClientProtocol(Protocol):
    """Protocol defining the interface of AsyncSalesforceClient for typing purposes."""
    base_url: str
    api_version: float
    api_usage: Any

    async def request(self, method: str, url: Any, resource_name: str = "", **kwargs) -> Any:
        ...

    async def get(self, url: str, **kwargs) -> Any:
        ...

    async def post(self, url: str, **kwargs) -> Any:
        ...

    @property
    def data_url(self) -> str:
        ...

    @property
    def sobjects_url(self) -> str:
        ...

    def composite_sobjects_url(self, sobject: str | None = None) -> str:
        ...

    async def __aenter__(self) -> "AsyncSalesforceClientProtocol":
        ...

    async def __aexit__(self, exc_type: Any = None, exc_value: Any = None, traceback: Any = None) -> None:
        ...


class SObjectAttributesProtocol(Protocol):
    """Protocol defining the structure of SObject attributes."""
    type: str
    connection: str


class SObjectProtocol(Protocol):
    """Protocol defining the interface of SObject classes for typing purposes."""
    _sf_attrs: SObjectAttributesProtocol
    fields: dict[str, Any]
    _client_connection: SalesforceClientProtocol

    @classmethod
    def get(cls, record_id: str, sf_client: Any = None) -> Any:
        ...

    @classmethod
    def fetch(cls, *ids: str, sf_client: Any = None, concurrency: int = 1,
              on_chunk_received: Any = None) -> list[Any]:
        ...

    def field_items(self) -> Any:
        ...
