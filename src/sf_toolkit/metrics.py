"""
Utility functions and types to assist in parsing API usage metadata
"""

from typing import TypedDict
from collections import namedtuple
import re

Usage = namedtuple("Usage", "used total")
PerAppUsage = namedtuple("PerAppUsage", "used total name")

ApiUsage = TypedDict(
    "ApiUsage", {"api-usage": Usage, "per-app-api-usage": PerAppUsage}, total=False
)


def parse_api_usage(sforce_limit_info: str):
    """
    Parse API usage and limits out of the Sforce-Limit-Info header
    Arguments:
    * sforce_limit_info: The value of response header 'Sforce-Limit-Info'
        Example 1: 'api-usage=18/5000'
        Example 2: 'api-usage=25/5000;
            per-app-api-usage=17/250(appName=sample-connected-app)'
    """
    result: ApiUsage = {}

    api_usage = re.match(
        r"[^-]?api-usage=(?P<used>\d+)/(?P<tot>\d+)", sforce_limit_info
    )
    pau = r".+per-app-api-usage=(?P<u>\d+)/(?P<t>\d+)\(appName=(?P<n>.+)\)"
    per_app_api_usage = re.match(pau, sforce_limit_info)

    if api_usage and api_usage.groups():
        groups = api_usage.groups()
        result["api-usage"] = Usage(used=int(groups[0]), total=int(groups[1]))
    if per_app_api_usage and per_app_api_usage.groups():
        groups = per_app_api_usage.groups()
        result["per-app-api-usage"] = PerAppUsage(
            used=int(groups[0]), total=int(groups[1]), name=groups[2]
        )
    return result
