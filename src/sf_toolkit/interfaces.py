from abc import ABC, abstractmethod
from httpx import AsyncClient, Client
from httpx._client import BaseClient  # type: ignore

from .auth.types import TokenRefreshCallback, SalesforceToken
from .apimodels import ApiVersion, UserInfo
from ._models import SObjectAttributes

class TokenRefreshCallbackMixin:
    token_refresh_callback: TokenRefreshCallback | None

    def handle_token_refresh(self, token: SalesforceToken):
        self.derive_base_url(token)
        if self.token_refresh_callback:
            self.token_refresh_callback(token)

    def set_token_refresh_callback(self, callback: TokenRefreshCallback):
        self.token_refresh_callback = callback

    def derive_base_url(self, session: SalesforceToken):
        self.base_url = f"https://{session.instance}"

class SalesforceApiHelpersMixin(BaseClient):
    DEFAULT_API_VERSION = 63.0
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
        return self.build_request("GET", "/oauth2/userinfo")

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

class I_AsyncSalesforceClient(
    TokenRefreshCallbackMixin,
    SalesforceApiHelpersMixin,
    AsyncClient,
    ABC):

    def unregister_parent(self) -> None:
        ...


class I_SalesforceClient(
    TokenRefreshCallbackMixin,
    SalesforceApiHelpersMixin,
    Client,
    ABC):

    @property
    @abstractmethod
    def as_async(self) -> I_AsyncSalesforceClient:
        ...



class I_SObject(ABC):

    @classmethod
    @abstractmethod
    def _client_connection(cls) -> I_SalesforceClient:
        ...

    @classmethod
    @property
    @abstractmethod
    def attributes(cls) -> SObjectAttributes:
        ...


    @classmethod
    @abstractmethod
    def keys(cls) -> frozenset[str]:
        ...
