from abc import ABCMeta
from enum import Enum
from functools import cached_property
from types import TracebackType
from typing import Any, ClassVar, Protocol, TypeVar
from typing_extensions import override

from httpx import URL, AsyncClient, Client, Request, Response

from .logger import getLogger
from .metrics import ApiUsage, parse_api_usage
from .exceptions import raise_for_status
from .auth import (
    SalesforceAuth,
    SalesforceLogin,
    SalesforceToken,
    TokenRefreshCallback,
)
from .apimodels import ApiVersion, UserInfo, OrgLimits

LOGGER = getLogger("client")

_T = TypeVar("_T")
_SCB = TypeVar("_SCB", bound="SalesforceClientBase")


class OrgType(Enum):
    PRODUCTION = "Production"
    SCRATCH = "Scratch"
    SANDBOX = "Sandbox"
    DEVELOPER = "Developer"


class ClientBaseProto(Protocol):
    _base_url: URL

    def _enforce_trailing_slash(self, url: URL) -> URL: ...

    def build_request(self, method: str, url: str) -> Request: ...


class SalesforceClientBase(ClientBaseProto, metaclass=ABCMeta):
    token_refresh_callback: TokenRefreshCallback | None = None
    api_version: ApiVersion | None = None
    _versions: dict[float, ApiVersion] | None = None
    _userinfo: UserInfo | None = None
    api_usage: ApiUsage | None = None
    connection_name: str

    DEFAULT_CONNECTION_NAME: ClassVar[str] = "default"

    def register(
        self: _SCB,
        api_version: ApiVersion | int | float | str | None = None,
        connection_name: str = DEFAULT_CONNECTION_NAME,
    ):
        if api_version is not None:
            self.api_version = ApiVersion.lazy_build(api_version)
        self.connection_name = connection_name
        type(self).register_connection(connection_name, self)

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls._connections: dict[str, "SalesforceClientBase"] = {}

    def handle_token_refresh(self, token: SalesforceToken):
        self._derive_base_url(token)
        if self.token_refresh_callback:
            self.token_refresh_callback(token)

    def set_token_refresh_callback(self, callback: TokenRefreshCallback):
        self.token_refresh_callback = callback

    def _derive_base_url(self, session: SalesforceToken):
        self._base_url = self._enforce_trailing_slash(session.instance)

    @property
    def org_type(self) -> OrgType:
        if not self._base_url:
            raise ValueError("Base URL is not set on the client.")
        if ".scratch." in self._base_url.host.lower():
            return OrgType.SCRATCH
        elif ".sandbox." in self._base_url.host.lower():
            return OrgType.SANDBOX
        elif self._base_url.host.lower().split(".", 1)[0].endswith("-dev-ed"):
            return OrgType.DEVELOPER
        else:
            return OrgType.PRODUCTION

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

    @classmethod
    def get_connection(cls: type[_SCB], name: str | None = None) -> _SCB:
        return cls._connections[name or cls.DEFAULT_CONNECTION_NAME]  # pyright: ignore[reportReturnType]

    @classmethod
    def register_connection(cls: type[_SCB], connection_name: str, instance: _SCB):
        if connection_name in cls._connections:
            raise KeyError(
                f"SalesforceClient connection '{connection_name}' has already been registered."
            )
        cls._connections[connection_name] = instance

    @classmethod
    def unregister_connection(cls: type[_SCB], name_or_instance: str | _SCB):
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


class AsyncSalesforceClient(AsyncClient, SalesforceClientBase):
    _auth: SalesforceAuth
    token_refresh_callback: TokenRefreshCallback | None

    def __init__(
        self,
        login: SalesforceLogin | None = None,
        token: SalesforceToken | None = None,
        token_refresh_callback: TokenRefreshCallback | None = None,
        api_version: ApiVersion | int | float | str | None = None,
        connection_name: str = SalesforceClientBase.DEFAULT_CONNECTION_NAME,
    ):
        assert login or token, (
            "Either auth or session parameters are required.\n"
            "Both are permitted simultaneously."
        )
        super().__init__(
            auth=SalesforceAuth(login, token, self.handle_token_refresh),
            headers={"Accept": "application/json"},
        )
        self.register(api_version, connection_name)
        if token:
            self._derive_base_url(token)
        self.token_refresh_callback = token_refresh_callback

    @override
    async def __aenter__(self):
        _ = await super().__aenter__()
        try:
            self._userinfo = UserInfo(
                **(await self.send(self._userinfo_request())).json()
            )
            if self.api_version:
                self.api_version = (await self.versions())[self.api_version.version]
            else:
                self.api_version = (await self.versions())[max(await self.versions())]
            LOGGER.info(
                "Logged into %s as %s (%s)",
                self.base_url,
                self._userinfo.name,
                self._userinfo.preferred_username,
            )
        except Exception as e:
            await self.__aexit__(type(e), e, e.__traceback__)
            raise
        return self

    @override
    async def aclose(self):
        self.unregister_connection(self.connection_name)
        self.unregister_connection(self)
        return await super().aclose()

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        self.unregister_connection(self.connection_name)
        self.unregister_connection(self)
        return await super().__aexit__(exc_type, exc_value, traceback)

    @override
    async def request(
        self, method: str, url: URL | str, resource_name: str = "", **kwargs: Any
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


class SalesforceClient(Client, SalesforceClientBase):
    token_refresh_callback: TokenRefreshCallback | None
    connection_name: str
    _auth: SalesforceAuth

    def __init__(
        self,
        connection_name: str = SalesforceClientBase.DEFAULT_CONNECTION_NAME,
        login: SalesforceLogin | None = None,
        token: SalesforceToken | None = None,
        token_refresh_callback: TokenRefreshCallback | None = None,
        api_version: ApiVersion | int | float | str | None = None,
        **kwargs: Any,
    ):
        assert login or token, (
            "Either auth or session parameters are required.\n"
            "Both are permitted simultaneously."
        )
        auth = SalesforceAuth(login, token, self.handle_token_refresh)
        super().__init__(auth=auth, **kwargs)
        self.register(connection_name=connection_name, api_version=api_version)
        if token:
            self._derive_base_url(token)
        self.token_refresh_callback = token_refresh_callback
        self.connection_name = connection_name

    @override
    def __str__(self):
        if not (isinstance(self.auth, SalesforceAuth) and self.auth.token is not None):
            return f"{type(self).__name__} ({self.connection_name})"
        return (
            f"{type(self).__name__} ({self.connection_name}) -> "
            f"{self.auth.token.instance.host} as {(_ui := self._userinfo) and _ui.preferred_username}"
        )

    def handle_async_clone_token_refresh(self, token: SalesforceToken):
        self._auth.token = token

    @override
    def __enter__(self):
        _ = Client.__enter__(self)
        try:
            self._userinfo = UserInfo(**self.send(self._userinfo_request()).json())
            if _av := getattr(self, "api_version", None):
                self.api_version = self.versions[_av.version]
            else:
                self.api_version = self.versions[max(self.versions)]
            LOGGER.info(
                "Logged into %s as %s (%s)",
                self.base_url,
                self._userinfo.name,
                self._userinfo.preferred_username,
            )
        except Exception as e:
            self.__exit__(type(e), e, e.__traceback__)
            raise
        return self

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        self.unregister_connection(self.connection_name)
        self.unregister_connection(self)
        return super().__exit__(exc_type, exc_value, traceback)

    @override
    def close(self):
        self.unregister_connection(self.connection_name)
        self.unregister_connection(self)
        return super().close()

    @override
    def request(
        self,
        method: str,
        url: URL | str,
        resource_name: str = "",
        response_status_raise: bool = True,
        **kwargs: Any,
    ) -> Response:
        response = super().request(method, url, **kwargs)

        if response_status_raise:
            raise_for_status(response, resource_name)

        sforce_limit_info: str | None = response.headers.get("Sforce-Limit-Info")
        if sforce_limit_info:
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
