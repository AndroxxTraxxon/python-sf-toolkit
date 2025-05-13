import asyncio
from functools import cached_property
from types import TracebackType

from httpx import URL, Response
from httpx._client import ClientState  # type: ignore

from .interfaces import I_AsyncSalesforceClient, I_SalesforceClient


from .logger import getLogger
from .metrics import parse_api_usage
from .exceptions import raise_for_status
from .auth import (
    SalesforceAuth,
    SalesforceLogin,
    SalesforceToken,
    TokenRefreshCallback,
)
from .apimodels import ApiVersion, UserInfo, OrgLimits

LOGGER = getLogger("client")


class AsyncSalesforceClient(I_AsyncSalesforceClient):
    _auth: SalesforceAuth

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
        super().__init__(
            auth=SalesforceAuth(login, token, self.handle_token_refresh),
            headers={"Accept": "application/json"},
        )
        if token:
            self._derive_base_url(token)
        self.token_refresh_callback = token_refresh_callback
        self.sync_parent = sync_parent

    def unregister_parent(self):
        self.sync_parent = None

    async def __aenter__(self):  # type: ignore
        if self._state == ClientState.UNOPENED:
            await super().__aenter__()
            self._userinfo = (await self.send(self._userinfo_request())).json(
                object_hook=ApiVersion
            )
            self._versions = (await self.send(self._versions_request())).json(
                object_hook=ApiVersion
            )
            if self.api_version:
                self.api_version = self._versions[self.api_version.version]
            else:
                self.api_version = self._versions[max(self._versions)]
            return self
            LOGGER.info(
                "Opened connection to %s as %s (%s) using API Version %s (%.01f)",
                self.base_url,
                self._userinfo.name,
                self._userinfo.preferred_username,
                self.api_version.label,
                self.api_version.version,
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

        if sforce_limit_info := response.headers.get("Sforce-Limit-Info"):
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
            float(version["version"]): ApiVersion(
                float(version["version"]), version["label"], version["url"]
            )
            for version in versions_data
        }


class SalesforceClient(I_SalesforceClient):
    token_refresh_callback: TokenRefreshCallback | None
    _auth: SalesforceAuth

    def __init__(
        self,
        connection_name: str = I_SalesforceClient.DEFAULT_CONNECTION_NAME,
        login: SalesforceLogin | None = None,
        token: SalesforceToken | None = None,
        token_refresh_callback: TokenRefreshCallback | None = None,
        headers={"Accept": "application/json"},
        **kwargs,
    ):
        assert login or token, (
            "Either auth or session parameters are required.\n"
            "Both are permitted simultaneously."
        )
        auth = SalesforceAuth(login, token, self.handle_token_refresh)
        super().__init__(auth=auth, **kwargs)
        if token:
            self._derive_base_url(token)
        self.token_refresh_callback = token_refresh_callback
        self._connection_name = connection_name

    def handle_async_clone_token_refresh(self, token: SalesforceToken):
        self._auth.token = token

    # caching this so that multiple calls don't generate new sessions.
    @property
    def as_async(self) -> I_AsyncSalesforceClient:
        a_client = getattr(self, "_async_session", None)
        if a_client is None:
            a_client = self._async_session = AsyncSalesforceClient(
                login=self._auth.login,
                token=self._auth.token,
                token_refresh_callback=self.handle_async_clone_token_refresh,
                sync_parent=self,
            )
        return a_client

    @as_async.deleter
    def as_async(self):
        self._async_session = None

    def __enter__(self):
        super().__enter__()
        try:
            self._userinfo = UserInfo(**self.send(self._userinfo_request()).json())
            if getattr(self, "api_version", None):
                self.api_version = self.versions[self.api_version.version]
            else:
                self.api_version = self.versions[max(self.versions)]
            LOGGER.info(
                "Logged into %s as %s (%s)",
                self.base_url,
                self._userinfo.name,
                self._userinfo.preferred_username,
            )
        except Exception as e:
            super().__exit__(type(e), e, e.__traceback__)
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        if self.as_async._state == ClientState.OPENED:
            self.as_async.unregister_parent()
            asyncio.run(self.as_async.__aexit__())
            del self.as_async
        return super().__exit__(exc_type, exc_value, traceback)

    def request(
        self,
        method: str,
        url: URL | str,
        resource_name: str = "",
        response_status_raise: bool = True,
        **kwargs,
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
            (f_ver := float(version["version"])): ApiVersion(
                f_ver, version["label"], version["url"]
            )
            for version in versions_data
        }

    def limits(self):
        """
        Returns a dictionary of API versions available in the org.

        Returns:
            OrgLimits: dict-like object of available limits
        """
        return OrgLimits(**self.get(self.data_url + "/limits/").json())

    # resources for the client
    @property
    def tooling(self) -> "ToolingResource":
        try:
            return self._tooling
        except AttributeError:
            if "Tooling" not in globals():
                global ToolingResource
                from .resources.tooling import ToolingResource
            self._tooling = ToolingResource(self)
            return self._tooling

    @property
    def metadata(self) -> "MetadataResource":
        try:
            return self._metadata
        except AttributeError:
            if "MetadataResource" not in globals():
                global MetadataResource
                from .resources.metadata import MetadataResource
            self._metadata = MetadataResource(self)
            return self._metadata

    @tooling.deleter
    def tooling(self):
        try:
            del self._tooling
        except AttributeError:
            pass
