from pathlib import Path
from shutil import which
from subprocess import run as subprocess_run
import os
import json

from httpx import URL

from ..logger import getLogger

from .types import SalesforceLogin, SalesforceToken
from sf_toolkit.auth.types import SalesforceTokenGenerator

LOGGER = getLogger("auth.cli")


def cli_login(
    alias_or_username: str | None = None, sf_exec_path: str | Path | None = None
) -> SalesforceLogin:
    if not sf_exec_path:
        sf_exec_path = which("sf") or which("sfdx")
        if not sf_exec_path:
            raise ValueError("Could not find `sf` executable.")
    elif isinstance(sf_exec_path, Path):
        sf_exec_path = str(sf_exec_path.resolve())

    def _cli_login() -> SalesforceTokenGenerator:
        """Fetches the authentication credentials from sf or sfdx command line tools."""
        LOGGER.info("Logging in via SF CLI at %s", sf_exec_path)
        command: list[str] = [sf_exec_path, "org", "display", "--json"]
        if alias_or_username and isinstance(alias_or_username, str):
            command.extend(["-o", alias_or_username])

        # the color shell configs can mess with JSON parsing, so just get rid of them.
        cmd_env = {
            key: value
            for key, value in os.environ.items()
            if "color" not in key.casefold()
        }

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
        # Normal orgs use 'connectedStatus': 'Connected'
        # Scratch orgs use 'status': 'Active'
        if (
            token_result.get("connectedStatus") != "Connected"
            and token_result.get("status") != "Active"
        ):
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
        return SalesforceToken(URL(instance_url), session_id)
        yield  # yield to make this a generator

    return _cli_login
