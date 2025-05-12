from abc import ABC, abstractmethod
from types import TracebackType
from typing import Iterable
from httpx import AsyncClient, Client
from httpx._client import BaseClient  # type: ignore

from .auth.types import TokenRefreshCallback, SalesforceToken
from .apimodels import ApiVersion, UserInfo
from ._models import SObjectAttributes


class TokenRefreshCallbackMixin(BaseClient):
    token_refresh_callback: TokenRefreshCallback | None

    def handle_token_refresh(self, token: SalesforceToken):
        self._derive_base_url(token)
        if self.token_refresh_callback:
            self.token_refresh_callback(token)

    def set_token_refresh_callback(self, callback: TokenRefreshCallback):
        self.token_refresh_callback = callback

    def _derive_base_url(self, session: SalesforceToken):
        self._base_url = self._enforce_trailing_slash(session.instance)


class SalesforceApiHelpersMixin(BaseClient):
    api_version: ApiVersion
    _versions: dict[float, ApiVersion]
    _userinfo: UserInfo

    def __init__(self, **kwargs):
        if "api_version" in kwargs:
            self.api_version = ApiVersion.lazy_build(kwargs["api_version"])

        super().__init__(**kwargs)

    @property
    def data_url(self):
        if not self.api_version:
            assert hasattr(self, "_versions") and self._versions, ""
            self.api_version = self._versions[max(self._versions)]
        return self.api_version.url

    def _userinfo_request(self):
        return self.build_request("GET", "/services/oauth2/userinfo")

    def _versions_request(self):
        return self.build_request("GET", "/services/data")

    @property
    def sobjects_url(self):
        return f"{self.data_url}/sobjects"

    def composite_sobjects_url(self, sobject: str | None = None):
        url = f"{self.data_url}/composite/sobjects"
        if sobject:
            url += "/" + sobject
        return url

    @property
    def tooling_url(self):
        return f"{self.data_url}/tooling"

    @property
    def tooling_sobjects_url(self):
        return f"{self.data_url}/tooling"

    @property
    def metadata_url(self):
        return f"{self.data_url}/metadata"


class I_AsyncSalesforceClient(
    TokenRefreshCallbackMixin, SalesforceApiHelpersMixin, AsyncClient, ABC
):
    def unregister_parent(self) -> None: ...


class I_SalesforceClient(
    TokenRefreshCallbackMixin, SalesforceApiHelpersMixin, Client, ABC
):
    _connections: dict[str, "I_SalesforceClient"] = {}
    _connection_name: str

    DEFAULT_CONNECTION_NAME = "default"

    @classmethod
    def get_connection(cls, name: str | None = None):
        if not name:
            name = cls.DEFAULT_CONNECTION_NAME
        return cls._connections[name]

    @property
    @abstractmethod
    def as_async(self) -> I_AsyncSalesforceClient: ...

    @classmethod
    def register_connection(cls, connection_name: str, instance: "I_SalesforceClient"):
        if connection_name in cls._connections:
            raise KeyError(
                f"SalesforceClient connection '{connection_name}' has already been registered."
            )
        cls._connections[connection_name] = instance

    @classmethod
    def unregister_connection(cls, name_or_instance: "str | I_SalesforceClient"):
        if isinstance(name_or_instance, str):
            names_to_unregister = [name_or_instance]
        else:
            names_to_unregister = [
                name
                for name, instance in cls._connections.items()
                if instance is name_or_instance
            ]
        for name in names_to_unregister:
            if name in cls._connections:
                del cls._connections[name]

    def __enter__(self):
        super().__enter__()
        self.register_connection(self._connection_name, self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        self.unregister_connection(self._connection_name)
        self.unregister_connection(self)
        return super().__exit__(exc_type, exc_value, traceback)


class I_SObject(ABC):
    attributes: SObjectAttributes

    @classmethod
    @abstractmethod
    def _client_connection(cls) -> I_SalesforceClient: ...

    @classmethod
    @abstractmethod
    def keys(cls) -> Iterable[str]: ...

    @classmethod
    @abstractmethod
    def query_fields(cls) -> Iterable[str]: ...
