import asyncio
from functools import cached_property
from types import TracebackType
from typing_extensions import override

from httpx import URL, Client, AsyncClient, Response
from httpx._client import ClientState, BaseClient  # type: ignore

from .logger import getLogger
from .metrics import parse_api_usage
from .exceptions import raise_for_status
from .auth import (
    SalesforceAuth,
    SalesforceLogin,
    SalesforceToken,
    TokenRefreshCallback,
)
from .apimodels import (
    ApiVersion,
    UserInfo
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

    async def __aenter__(self):
        if not isinstance(self, AsyncClient):
            raise TypeError(f"{type(self)} {self} is not an instance of AsyncClient")
        try:
            await super().__aenter__()  # type: ignore
        except:
            pass
        self._userinfo = await self.send_request(self._userinfo_request()).json(object_hook=ApiVersion)  # type: ignore
        self._versions = (await self.send(self._versions_request())).json(object_hook=ApiVersion)
        if self.api_version:
            self.api_version = self._versions[self.api_version.version]
        else:
            self.api_version = self._versions[max(self._versions)]
        return self

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
        sync_parent: "SalesforceClient | None" = None,
    ):
        assert login or token, (
            "Either auth or session parameters are required.\n"
            "Both are permitted simultaneously."
        )
        super().__init__(auth=SalesforceAuth(login, token, self.handle_token_refresh))
        if token:
            self.derive_base_url(token)
        self.token_refresh_callback = token_refresh_callback
        self.sync_parent = sync_parent


    async def __aenter__(self):  # type: ignore
        if self._state == ClientState.UNOPENED:
            await super().__aenter__()
            LOGGER.info(
                "Opened connection to %s as %s (%s) using API Version %s (%.01f)",
                self.base_url,
                self._userinfo.name,
                self._userinfo.preferred_username,
                self.api_version.label,
                self.api_version.version
            )

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if self.sync_parent:
            return None
        return await super().__aexit__(exc_type, exc_value, traceback)

    async def request(
        self, method: str, url: URL | str, resource_name: str = "", **kwargs
    ) -> Response:
        response = await super().request(method, url, **kwargs)

        raise_for_status(response, resource_name)


        if (sforce_limit_info := response.headers.get("Sforce-Limit-Info")):
            self.api_usage = parse_api_usage(sforce_limit_info)
        return response

    async def versions(self) -> dict[float, ApiVersion]:
        """
        Returns a dictionary of API versions available in the org asynchronously.
        https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/dome_versions.htm

        Returns:
            dict[float, ApiVersion]: Dictionary of available API versions
        """
        response = await self.request("GET", "/services/data")
        versions_data = response.json()
        return {
            float(version["version"]): ApiVersion(float(version["version"]), version["label"], version["url"])
            for version in versions_data
        }


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
            sync_parent=self,
        )

    def __enter__(self):
        super().__enter__()
        self._userinfo = UserInfo(**self.send(self._userinfo_request()).json())
        if getattr(self, "api_version", None):
            self.api_version = self.versions[self.api_version.version]
        else:
            self.api_version = self.versions[max(self.versions)]
        return self
        LOGGER.info(
            "Logged into %s as %s (%s)",
            self.base_url,
            self._userinfo.name,
            self._userinfo.preferred_username
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if self.as_async._state == ClientState.OPENED:
            self.as_async.sync_parent = None
            asyncio.run(self.as_async.__aexit__())
            del self.as_async
        return super().__exit__(exc_type, exc_value, traceback)

    def request(
        self,
        method: str,
        url: URL | str,
        resource_name: str = "",
        response_status_raise: bool = True,
        **kwargs
    ) -> Response:
        response = super().request(method, url, **kwargs)

        if response_status_raise:
            raise_for_status(response, resource_name)

        sforce_limit_info = response.headers.get("Sforce-Limit-Info")
        if sforce_limit_info and isinstance(sforce_limit_info, str):
            self.api_usage = parse_api_usage(sforce_limit_info)
        return response

    @cached_property
    def versions(self) -> dict[float, ApiVersion]:
        """
        Returns a dictionary of API versions available in the org.

        Returns:
            list[ApiVersion]: List of available API versions
        """
        response = self.request("GET", "/services/data")
        versions_data = response.json()
        return {
            (f_ver := float(version["version"])): ApiVersion(f_ver, version["label"], version["url"])
            for version in versions_data
        }
