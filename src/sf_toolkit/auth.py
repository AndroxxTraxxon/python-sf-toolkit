# import jwt
from collections.abc import Generator
import json
import os
from pathlib import Path
from shutil import which
from subprocess import run as subprocess_run
import typing

import httpx

from .logger import getLogger

LOGGER = getLogger("auth")


class SalesforceToken(typing.NamedTuple):
    instance: str
    token: str


SalesforceLogin = typing.Callable[
    [], Generator[httpx.Request | None, httpx.Response, SalesforceToken]
]

TokenRefreshCallback = typing.Callable[[SalesforceToken], typing.Any]


def cli_login(
    alias_or_username: str | None = None, sf_exec_path: str | Path | None = None
) -> SalesforceLogin:
    if not sf_exec_path:
        sf_exec_path = which("sf") or which("sfdx")
        if not sf_exec_path:
            raise ValueError("Could not find sf executable.")
    elif isinstance(sf_exec_path, Path):
        sf_exec_path = str(sf_exec_path.resolve())

    def _cli_login():
        """Fetches the authentication credentials from sf or sfdx command line tools."""
        LOGGER.info("Logging in via SF CLI at %s", sf_exec_path)
        yield  # yield to make this a generator
        command: list[str] = [sf_exec_path, "org", "display", "--json"]
        if alias_or_username:
            command.extend(["-o", alias_or_username])

        # ipython messes with environment variables that causes the json parse to fail
        # we're preserving environment, but un-setting these three variables
        # when they are present
        cmd_env = {**os.environ}
        color_vars = (
            "CLICOLOR",
            "FORCE_COLOR",
            "CLICOLOR_FORCE",
        )
        for var in color_vars:
            if var in cmd_env:
                cmd_env[var] = "0"

        result = subprocess_run(command, check=False, capture_output=True, env=cmd_env)

        output = json.loads(result.stdout)
        if output["status"] != 0:
            exception = type(output["name"], (Exception,), {})
            raise exception(
                "Failed to get credentials for org "
                + (alias_or_username or "[default]")
                + ":\n"
                + output["message"]
                .encode("raw_unicode_escape")
                .decode("unicode_escape")
            )
        token_result = output["result"]
        if token_result["connectedStatus"] != "Connected":
            exception = type(token_result["connectedStatus"], (Exception,), {})
            raise exception(
                "Check SF CLI. Unable to connect to "
                + token_result["instanceUrl"]
                + " as "
                + token_result["username"]
                + ":\n"
                + "; ".join(output["warnings"][:-1])
            )
        session_id = token_result["accessToken"]
        instance_url = token_result["instanceUrl"]
        sf_instance = instance_url.replace("http://", "").replace("https://", "")

        return SalesforceToken(sf_instance, session_id)

    return _cli_login


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
        if self.token is None:
            assert self.login is not None, "No login method provided"
            try:
                for login_request in (login_flow := self.login()):
                    if isinstance(login_request, httpx.Request):
                        login_response = yield login_request
                        login_flow.send(login_response)

            except StopIteration as login_result:
                new_token: SalesforceToken = login_result.value
                self.token = new_token
                if self.callback is not None:
                    self.callback(new_token)
            assert self.token is not None, "Failed to perform initial login"

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
                new_token: SalesforceToken = login_result.value
                self.token = new_token
                if self.callback is not None:
                    self.callback(new_token)

            request.headers["Authorization"] = f"Bearer {self.token.token}"
            response = yield request
