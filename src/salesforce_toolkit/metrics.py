"""
Utility functions and types to assist in parsing API usage metadata
"""

from typing import NamedTuple
import re


class Usage(NamedTuple):
    used: int
    total: int


class PerAppUsage(NamedTuple):
    used: int
    total: int
    name: str


app_usage_pattern = re.compile(r"[^-]?api-usage=(?P<used>\d+)/(?P<tot>\d+)")
per_app_usage_pattern = re.compile(
    r".+per-app-api-usage=(?P<u>\d+)/(?P<t>\d+)\(appName=(?P<n>.+)\)"
)


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
    if (match := app_usage_pattern.match(sforce_limit_info)) and (
        groups := match.groups()
    ):
        app_usage = Usage(used=int(groups[0]), total=int(groups[1]))

    if (match := per_app_usage_pattern.match(sforce_limit_info)) and (
        groups := match.groups()
    ):
        per_app_usage = PerAppUsage(
            used=int(groups[0]), total=int(groups[1]), name=groups[2]
        )

    return ApiUsage(app_usage, per_app_usage)
