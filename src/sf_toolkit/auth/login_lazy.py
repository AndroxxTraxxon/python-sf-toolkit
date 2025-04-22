__all__ = ("lazy_login",)

from .login_cli import cli_login
from .login_oauth import lazy_oauth_login
from .login_soap import lazy_soap_login
from .types import LazyParametersMissing


def lazy_login(**kwargs):
    if "sf_cli_alias" in kwargs:
        return cli_login(
            kwargs.pop("sf_cli_alias"), kwargs.pop("sf_cli_exec_path", None)
        )

    elif any(
        key in kwargs for key in ["consumer_key", "private_key", "consumer_secret"]
    ):
        return lazy_oauth_login(**kwargs)
    elif all(key in kwargs for key in ["username", "password"]):
        # All SOAP login methods require at least username and password
        return lazy_soap_login(**kwargs)
    else:
        raise LazyParametersMissing(
            "Could not determine authentication method from provided parameters.\n"
            f"Provided parameters: {', '.join(kwargs.keys())}\n"
            "Please provide appropriate parameters for CLI, OAuth, or SOAP authentication."
        )
