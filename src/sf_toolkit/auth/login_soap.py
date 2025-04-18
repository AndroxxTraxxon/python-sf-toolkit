"""Login classes and functions for salesforce-toolkit

Based on simple-salesforce 1.12.5
"""

import lxml.etree as etree
from html import escape

import httpx

from .types import SalesforceLogin, SalesforceToken, SalesforceTokenGenerator

from .soap_templates import (
    SECURITY_TOKEN_TEMPLATE,
    IP_FILTERING_ORG_ID_TEMPLATE,
    IP_FILTERING_NON_SERVICE_TEMPLATE,
)
from ..exceptions import SalesforceAuthenticationFailed

DEFAULT_CLIENT_ID_PREFIX = "sf-toolkit"


def get_xml_element_value(xmlString: bytes | str, elementName: str) -> str | None:
    """
    Extracts an element value from an XML string.

    For example, invoking
    get_element_value(
        '<?xml version="1.0" encoding="UTF-8"?><foo>bar</foo>', 'foo')
    should return the value 'bar'.
    """
    if isinstance(xmlString, str):
        xmlString = xmlString.encode('utf-8')

    root = etree.fromstring(xmlString)

    elements = root.findall(f".//{{*}}{elementName}")

    if elements and elements[0].text:
        return elements[0].text
    return None

def soap_login(domain: str, sf_version: float | int, request_body: str) -> SalesforceTokenGenerator:
    """Process SOAP specific login workflow."""
    soap_url = httpx.URL(f"https://{domain}.salesforce.com/services/Soap/u/{sf_version:.01f}")
    response: httpx.Response = yield httpx.Request(
        "POST",
        soap_url,
        content=request_body,
        headers={
            "content-type": "text/xml",
            "charset": "UTF-8",
            "SOAPAction": "login",
        },
    )

    if not response.is_success:
        except_code = get_xml_element_value(
            response.text, "sf:exceptionCode"
        )
        except_msg = get_xml_element_value(
            response.text, "sf:exceptionMessage"
        )
        raise SalesforceAuthenticationFailed(except_code, except_msg)

    session_id = get_xml_element_value(response.text, "sessionId")
    server_url = get_xml_element_value(response.text, "serverUrl")
    assert server_url is not None, "Unable to find Server URL"
    assert session_id is not None, "Unable to find Session ID"

    return SalesforceToken(httpx.URL(server_url), session_id)


def security_token_login(
    username: str,
    password: str,
    security_token: str,
    client_id: str | None = None,
    domain: str = 'login',
    api_version: float | int = 63.0
) -> SalesforceLogin:
    if client_id:
        client_id = DEFAULT_CLIENT_ID_PREFIX + "/" +client_id
    else:
        client_id = DEFAULT_CLIENT_ID_PREFIX

    username = escape(username)
    password = escape(password)

    login_soap_request_body = SECURITY_TOKEN_TEMPLATE.format(
        client_id=client_id,
        security_token=security_token,
        username=username,
        password=password,
    )
    return lambda: soap_login(
        domain,
        api_version,
        login_soap_request_body,
    )


def ip_filtering_org_login(
    username: str,
    password: str,
    organizationId: str,
    client_id: str | None = None,
    domain: str = 'login',
    api_version: float | int = 63.0
) -> SalesforceLogin:
    if client_id:
        client_id = DEFAULT_CLIENT_ID_PREFIX + "/" +client_id
    else:
        client_id = DEFAULT_CLIENT_ID_PREFIX

    username = escape(username)
    password = escape(password)

    login_soap_request_body = IP_FILTERING_ORG_ID_TEMPLATE.format(
        client_id=client_id,
        organizationId=organizationId,
        username=username,
        password=password,
    )
    return lambda: soap_login(
        domain,
        api_version,
        login_soap_request_body,
    )



def ip_filtering_non_service_login(
    username: str,
    password: str,
    client_id: str | None = None,
    domain: str = 'login',
    api_version: float | int = 63.0,
) -> SalesforceLogin:
    if client_id:
        client_id = DEFAULT_CLIENT_ID_PREFIX + "/" +client_id
    else:
        client_id = DEFAULT_CLIENT_ID_PREFIX

    username = escape(username)
    password = escape(password)

    login_soap_request_body = IP_FILTERING_NON_SERVICE_TEMPLATE.format(
        client_id=client_id,
        username=username,
        password=password,
    )
    return lambda: soap_login(
        domain,
        api_version,
        login_soap_request_body,
    )
