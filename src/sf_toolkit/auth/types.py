import typing
import httpx

class SalesforceToken(typing.NamedTuple):
    instance: httpx.URL
    token: str


SalesforceLogin = typing.Callable[
    [], typing.Generator[httpx.Request | None, httpx.Response, SalesforceToken]
]

TokenRefreshCallback = typing.Callable[[SalesforceToken], typing.Any]

__all__ = [
    "SalesforceToken",
    "SalesforceLogin",
    "TokenRefreshCallback"
]
