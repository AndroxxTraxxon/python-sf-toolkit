import asyncio
from functools import cached_property
from types import TracebackType

from httpx import URL, Client, AsyncClient, Response
from httpx._client import ClientState

from .logger import getLogger
from .metrics import parse_api_usage
from .exceptions import build_salesforce_exception
from .auth import (
    SalesforceAuth,
    SalesforceLogin,
    SalesforceToken,
    TokenRefreshCallback,
)

LOGGER = getLogger("client")


class TokenRefreshCallbackMixin:
    token_refresh_callback: TokenRefreshCallback | None

    def handle_token_refresh(self, token: SalesforceToken):
        self.derive_base_url(token)
        if self.token_refresh_callback:
            self.token_refresh_callback(token)

    def set_token_refresh_callback(self, callback: TokenRefreshCallback):
        self.token_refresh_callback = callback

    def derive_base_url(self, session: SalesforceToken):
        self.base_url = f"https://{session.instance}/services"


class SalesforceApiHelpersMixin:
    DEFAULT_API_VERSION = 63.0
    api_version: float

    def __init__(self, **kwargs):
        self.api_version = kwargs.pop("api_version", self.DEFAULT_API_VERSION)
        super().__init__(**kwargs)

    @property
    def data_url(self):
        return f"/data/v{self.api_version:.01f}"

    @property
    def sobjects_url(self):
        return f"{self.data_url}/sobjects"

    def composite_sobjects_url(self, sobject: str | None = None):
        url = f"{self.data_url}/composite/sobjects"
        if sobject:
            url += "/" + sobject
        return url


class AsyncSalesforceClient(
    AsyncClient, TokenRefreshCallbackMixin, SalesforceApiHelpersMixin
):
    auth: SalesforceAuth  # type: ignore

    def __init__(
        self,
        login: SalesforceLogin | None = None,
        token: SalesforceToken | None = None,
        token_refresh_callback: TokenRefreshCallback | None = None,
        has_sync_parent: bool = False
    ):
        assert login or token, (
            "Either auth or session parameters are required.\n"
            "Both are permitted simultaneously."
        )
        super().__init__(auth=SalesforceAuth(login, token, self.handle_token_refresh))
        if token:
            self.derive_base_url(token)
        self.token_refresh_callback = token_refresh_callback
        self.has_sync_parent = has_sync_parent

    async def __aenter__(self):
        if self._state == ClientState.UNOPENED:
            await super().__aenter__()
            userinfo = (await self.get("/oauth2/userinfo")).json()
            LOGGER.info(
                "Logged into %s as %s (%s)",
                self.base_url,
                userinfo["name"],
                userinfo["preferred_username"],
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if self.has_sync_parent:
            return None
        return await super().__aexit__(exc_type, exc_value, traceback)

    async def request(
        self, method: str, url: URL | str, resource_name: str = "", **kwargs
    ) -> Response:
        response = await super().request(method, url, **kwargs)

        if not response.is_success:
            raise build_salesforce_exception(response, resource_name)

        sforce_limit_info = response.headers.get("Sforce-Limit-Info")
        if sforce_limit_info:
            self.api_usage = parse_api_usage(sforce_limit_info)
        return response


class SalesforceClient(Client, TokenRefreshCallbackMixin, SalesforceApiHelpersMixin):
    token_refresh_callback: TokenRefreshCallback | None
    auth: SalesforceAuth  # type: ignore
    DEFAULT_CONNECTION_NAME = "default"

    _connections: dict[str, "SalesforceClient"] = {}

    @classmethod
    def get_connection(cls, name: str):
        return cls._connections["name"]

    def __init__(
        self,
        connection_name: str = DEFAULT_CONNECTION_NAME,
        login: SalesforceLogin | None = None,
        token: SalesforceToken | None = None,
        token_refresh_callback: TokenRefreshCallback | None = None,
        **kwargs,
    ):
        assert login or token, (
            "Either auth or session parameters are required.\n"
            "Both are permitted simultaneously."
        )
        auth = SalesforceAuth(login, token, self.handle_token_refresh)
        super().__init__(auth=auth, **kwargs)
        if token:
            self.derive_base_url(token)
        self.token_refresh_callback = token_refresh_callback

        _conns = type(self)._connections
        if connection_name in _conns:
            raise KeyError(
                f"SalesforceClient connection '{connection_name}' has already been registered."
            )
        _conns[connection_name] = self

    def handle_async_clone_token_refresh(self, token: SalesforceToken):
        self.auth.token = token

    # caching this so that multiple calls don't generate new sessions.
    @cached_property
    def as_async(self) -> AsyncSalesforceClient:
        return AsyncSalesforceClient(
            login=self.auth.login,
            token=self.auth.token,
            token_refresh_callback=self.handle_async_clone_token_refresh,
        )

    def __enter__(self):
        super().__enter__()
        userinfo = self.get("/oauth2/userinfo").json()
        LOGGER.info(
            "Logged into %s as %s (%s)",
            self.base_url,
            userinfo["name"],
            userinfo["preferred_username"],
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if self.as_async._state == ClientState.OPENED:
            asyncio.run(self.as_async.__aexit__())
        return super().__exit__(exc_type, exc_value, traceback)

    def request(
        self, method: str, url: URL | str, resource_name: str = "", **kwargs
    ) -> Response:
        response = super().request(method, url, **kwargs)

        if not response.is_success:
            raise build_salesforce_exception(response, resource_name)

        sforce_limit_info = response.headers.get("Sforce-Limit-Info")
        if sforce_limit_info:
            self.api_usage = parse_api_usage(sforce_limit_info)
        return response
