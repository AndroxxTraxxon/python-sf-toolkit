"""
Utility functions and types to assist in parsing API usage metadata
"""

from typing import NamedTuple


class Usage(NamedTuple):
    used: int
    total: int


class PerAppUsage(NamedTuple):
    used: int
    total: int
    name: str


class ApiUsage(NamedTuple):
    api_usage: Usage | None
    per_app_api_usage: PerAppUsage | None


def parse_api_usage(sforce_limit_info: str):
    """
    Parse API usage and limits out of the Sforce-Limit-Info header
    Arguments:
    * sforce_limit_info: The value of response header 'Sforce-Limit-Info'
        Example 1: 'api-usage=18/5000'
        Example 2: 'api-usage=25/5000;
            per-app-api-usage=17/250(appName=sample-connected-app)'
    """
    app_usage, per_app_usage = None, None
    for item in sforce_limit_info.split(";"):
        try:
            item = item.strip()
            if not item:
                continue

            type, usage = item.split("=", maxsplit=1)
            if type.startswith("per-app-"):
                usage, appname = usage.split("(", maxsplit=1)
                appname = appname.removeprefix("appName=").removesuffix(")")
                used, total = map(int, usage.split("/", maxsplit=1))
                per_app_usage = PerAppUsage(used, total, appname)
            else:
                used, total = map(int, usage.split("/", maxsplit=1))
                app_usage = Usage(used, total)
        except ValueError:
            continue
    return ApiUsage(app_usage, per_app_usage)
