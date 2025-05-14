import base64
from html import unescape
from json import JSONDecodeError
import time
import warnings

import httpx
import jwt

from sf_toolkit.exceptions import SalesforceAuthenticationFailed

from .types import (
    AuthMissingResponse,
    LazyParametersMissing,
    SalesforceLogin,
    SalesforceToken,
    SalesforceTokenGenerator,
)


def token_login(
    domain: str,
    token_data: dict[str, str],
    consumer_key: str,
    headers: dict[str, str] | None = None,
) -> SalesforceTokenGenerator:
    """Process OAuth 2.0 JWT Bearer Token Flow."""
    response: httpx.Response = yield httpx.Request(
        "POST",
        f"https://{domain}.salesforce.com/services/oauth2/token",
        data=token_data,
        headers=headers,
    )

    if not response:
        raise AuthMissingResponse("No response received")

    try:
        response.read()
        json_response = response.json()
    except JSONDecodeError as exc:
        raise SalesforceAuthenticationFailed(
            response.status_code, response.text
        ) from exc

    if response.status_code != 200:
        except_code = json_response.get("error")
        except_msg = json_response.get("error_description")
        if except_msg == "user hasn't approved this consumer":
            auth_url = (
                f"https://{domain}.salesforce.com/services/oauth2/"
                "authorize?response_type=code&client_id="
                f"{consumer_key}&redirect_uri=<approved URI>"
            )
            warnings.warn(
                f"""
    If your connected app policy is set to "All users may
    self-authorize", you may need to authorize this
    application first. Browse to
    {auth_url}
    in order to Allow Access. Check first to ensure you have a valid
    <approved URI>."""
            )
        raise SalesforceAuthenticationFailed(except_code, except_msg)

    access_token = json_response.get("access_token")
    instance_url = json_response.get("instance_url")
    return SalesforceToken(httpx.URL(instance_url), access_token)


def password_login(
    username: str,
    password: str,
    consumer_key: str,
    consumer_secret: str,
    domain: str = "login",
) -> SalesforceLogin:
    """Process OAuth 2.0 Password Flow."""

    domain = domain.removesuffix(".salesforce.com")
    return lambda: token_login(
        domain,
        {
            "grant_type": "password",
            "username": unescape(username),
            "password": unescape(password) if password else "",
            "client_id": consumer_key,
            "client_secret": consumer_secret,
        },
        consumer_key,
        None,
    )


def client_credentials_flow_login(
    consumer_key: str, consumer_secret: str, domain: str
) -> SalesforceLogin:
    """Process OAuth 2.0 Client Credentials Flow."""

    domain = domain.removesuffix(".salesforce.com")
    token_data = {"grant_type": "client_credentials"}
    authorization = f"{consumer_key}:{consumer_secret}"
    encoded = base64.b64encode(authorization.encode()).decode()
    return lambda: token_login(
        domain, token_data, consumer_key, headers={"Authorization": f"Basic {encoded}"}
    )


def public_key_auth_login(
    username: str, consumer_key: str, private_key: bytes | str, domain: str = "login"
) -> SalesforceLogin:
    """Process OAuth 2.0 Public Key JWT Flow."""

    domain = domain.removesuffix(".salesforce.com")

    def _token_login():
        return token_login(
            domain,
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt.encode(
                    {
                        "iss": consumer_key,
                        "sub": username,
                        "aud": f"https://{domain}.salesforce.com",
                        "exp": int(time.time()) + 3600,
                    },
                    private_key,
                    algorithm="RS256",
                ),
            },
            consumer_key,
        )

    return _token_login


def lazy_oauth_login(**kwargs):
    """Determine which login method to use based on the provided kwargs."""
    if "private_key" in kwargs:
        # Public Key JWT Flow
        return public_key_auth_login(
            username=kwargs["username"],
            consumer_key=kwargs["consumer_key"],
            private_key=kwargs["private_key"],
            domain=kwargs.get("domain", "login"),
        )
    elif "consumer_secret" in kwargs and "username" in kwargs and "password" in kwargs:
        # Password Flow
        return password_login(
            username=kwargs["username"],
            password=kwargs["password"],
            consumer_key=kwargs["consumer_key"],
            consumer_secret=kwargs["consumer_secret"],
            domain=kwargs.get("domain", "login"),
        )
    elif "consumer_secret" in kwargs and "username" not in kwargs:
        # Client Credentials Flow
        return client_credentials_flow_login(
            consumer_key=kwargs["consumer_key"],
            consumer_secret=kwargs["consumer_secret"],
            domain=kwargs.get("domain", "login"),
        )
    else:
        raise LazyParametersMissing(
            "Unable to determine authentication method from provided parameters. "
            "Please provide appropriate parameters for one of the supported flows."
        )
