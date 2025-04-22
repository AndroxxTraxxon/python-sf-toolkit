import typing
import httpx


class LazyParametersMissing(RuntimeError):
    pass


class AuthMissingResponse(RuntimeError):
    pass


class SalesforceToken(typing.NamedTuple):
    instance: httpx.URL
    token: str


SalesforceTokenGenerator = typing.Generator[
    httpx.Request | None, httpx.Response | None, SalesforceToken
]

SalesforceLogin = typing.Callable[[], SalesforceTokenGenerator]

TokenRefreshCallback = typing.Callable[[SalesforceToken], typing.Any]

__all__ = ["SalesforceToken", "SalesforceLogin", "TokenRefreshCallback"]
