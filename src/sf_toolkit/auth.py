
# import jwt
import json
import os
from pathlib import Path
from shutil import which
from subprocess import run as subprocess_run
from typing import Callable, NamedTuple

from .logger import getLogger

LOGGER = getLogger("auth")

class SfSessionId(NamedTuple):
    instance: str
    session_id: str

SalesforceAuth = Callable[[], SfSessionId]

def cli_login(alias_or_username: str | None = None, sf_exec_path: str | Path | None = None):
    if not sf_exec_path:
        sf_exec_path = which("sf") or which("sfdx")
        if not sf_exec_path:
            raise ValueError("Could not find sf executable.")
    elif isinstance(sf_exec_path, Path):
        sf_exec_path = str(sf_exec_path.resolve())

    def _cli_login():
        """Fetches the authentication credentials from sf or sfdx command line tools."""

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
                + output["message"].encode("raw_unicode_escape").decode("unicode_escape")
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

        return SfSessionId(sf_instance, session_id)

    return _cli_login
