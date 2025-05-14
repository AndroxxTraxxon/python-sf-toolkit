import typing

import httpx

from ..logger import getLogger
from .types import SalesforceLogin, SalesforceToken, TokenRefreshCallback

LOGGER = getLogger("auth")


class SalesforceAuth(httpx.Auth):
    login: SalesforceLogin | None
    callback: TokenRefreshCallback | None
    token: SalesforceToken | None

    def __init__(
        self,
        login: SalesforceLogin | None = None,
        session_token: SalesforceToken | None = None,
        callback: TokenRefreshCallback | None = None,
    ):
        self.login = login
        self.token = session_token
        self.callback = callback

    def auth_flow(
        self, request: httpx.Request
    ) -> typing.Generator[httpx.Request, httpx.Response, None]:
        new_token: SalesforceToken
        if self.token is None or request.url.is_relative_url:
            assert self.login is not None, "No login method provided"
            try:
                login_flow = self.login()
                login_request = next(login_flow)
                while True:
                    if login_request is not None:
                        login_response = yield login_request
                        login_request = login_flow.send(login_response)
                    else:
                        login_request = next(login_flow)

            except StopIteration as login_result:
                new_token = login_result.value
                self.token = SalesforceToken(*new_token)
                if self.callback is not None:
                    self.callback(new_token)
            assert self.token is not None, "Failed to perform initial login"

        if request.url.is_relative_url:
            absolute_url = self.token.instance.raw_path + request.url.raw_path.lstrip(
                b"/"
            )
            request.url = self.token.instance.copy_with(raw_path=absolute_url)
            request._prepare({**request.headers})

        request.headers["Authorization"] = f"Bearer {self.token.token}"
        response = yield request

        if (
            response.status_code == 401
            and self.login
            and response.json()[0]["errorDetails"] == "INVALID_SESSION_ID"
        ):
            try:
                for login_request in (login_flow := self.login()):
                    if login_request is not None:
                        login_response = yield login_request
                        login_flow.send(login_response)

            except StopIteration as login_result:
                new_token = login_result.value
                self.token = new_token
                if self.callback is not None:
                    self.callback(new_token)

            request.headers["Authorization"] = f"Bearer {self.token.token}"
            response = yield request
