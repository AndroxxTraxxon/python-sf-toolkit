import typing
import httpx


class SalesforceToken(typing.NamedTuple):
    instance: httpx.URL
    token: str


SalesforceTokenGenerator = typing.Generator[httpx.Request | None, httpx.Response, SalesforceToken]

SalesforceLogin = typing.Callable[
    [], SalesforceTokenGenerator
]

TokenRefreshCallback = typing.Callable[[SalesforceToken], typing.Any]

__all__ = ["SalesforceToken", "SalesforceLogin", "TokenRefreshCallback"]
