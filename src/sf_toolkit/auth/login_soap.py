"""Login classes and functions for salesforce-toolkit

Based on simple-salesforce 1.12.5
"""

import lxml.etree as etree
from html import escape

import httpx

from .types import SalesforceLogin, SalesforceToken, SalesforceTokenGenerator

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

XML_NS = "sf"

def soap_login(domain: str, sf_version: float | int, request_body: str) -> SalesforceTokenGenerator:
    """Process SOAP specific login workflow."""
    soap_url = httpx.URL(f"https://{domain}.salesforce.com/services/Soap/u/{sf_version:.01f}")
    response = yield httpx.Request(
        "POST",
        soap_url,
        content=request_body,
        headers={
            "content-type": "text/xml",
            "charset": "UTF-8",
            "SOAPAction": "login",
        },
    )
    if not response:
        raise ValueError("No response received")

    if not response.is_success:
        except_code = get_xml_element_value(
            response.text, f"{XML_NS}:exceptionCode"
        )
        except_msg = get_xml_element_value(
            response.text, f"{XML_NS}:exceptionMessage"
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

    login_soap_request_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<env:Envelope
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:partner.soap.sforce.com">
    <env:Header>
        <urn:CallOptions>
            <urn:client>{client_id}</urn:client>
            <urn:defaultNamespace>{XML_NS}</urn:defaultNamespace>
        </urn:CallOptions>
    </env:Header>
    <env:Body>
        <n1:login xmlns:n1="urn:partner.soap.sforce.com">
            <n1:username>{username}</n1:username>
            <n1:password>{password}{security_token}</n1:password>
        </n1:login>
    </env:Body>
</env:Envelope>"""
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

    login_soap_request_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<soapenv:Envelope
        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:partner.soap.sforce.com">
    <soapenv:Header>
        <urn:CallOptions>
            <urn:client>{client_id}</urn:client>
            <urn:defaultNamespace>{XML_NS}</urn:defaultNamespace>
        </urn:CallOptions>
        <urn:LoginScopeHeader>
            <urn:organizationId>{organizationId}</urn:organizationId>
        </urn:LoginScopeHeader>
    </soapenv:Header>
    <soapenv:Body>
        <urn:login>
            <urn:username>{username}</urn:username>
            <urn:password>{password}</urn:password>
        </urn:login>
    </soapenv:Body>
</soapenv:Envelope>"""
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

    login_soap_request_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<soapenv:Envelope
        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:urn="urn:partner.soap.sforce.com">
    <soapenv:Header>
        <urn:CallOptions>
            <urn:client>{client_id}</urn:client>
            <urn:defaultNamespace>{XML_NS}</urn:defaultNamespace>
        </urn:CallOptions>
    </soapenv:Header>
    <soapenv:Body>
        <urn:login>
            <urn:username>{username}</urn:username>
            <urn:password>{password}</urn:password>
        </urn:login>
    </soapenv:Body>
</soapenv:Envelope>"""
    return lambda: soap_login(
        domain,
        api_version,
        login_soap_request_body,
    )


def lazy_soap_login(**kwargs):
    """
    Infer which SOAP login flow should be used based on the parameters provided.

    This function examines the kwargs to determine whether to use security_token_login,
    ip_filtering_org_login, or ip_filtering_non_service_login.

    Parameters are the same as the underlying login functions, with required parameters
    determined by the login flow chosen.

    Returns:
        SalesforceLogin: A callable that will perform the login workflow
    """
    # Username and password are always required
    if 'username' not in kwargs or 'password' not in kwargs:
        raise ValueError("Username and password are required parameters")

    # If security_token is provided, use security_token_login
    if 'security_token' in kwargs:
        return security_token_login(
            username=kwargs['username'],
            password=kwargs['password'],
            security_token=kwargs['security_token'],
            client_id=kwargs.get('client_id'),
            domain=kwargs.get('domain', 'login'),
            api_version=kwargs.get('api_version', 63.0)
        )

    # If organizationId is provided, use ip_filtering_org_login
    elif 'organizationId' in kwargs:
        return ip_filtering_org_login(
            username=kwargs['username'],
            password=kwargs['password'],
            organizationId=kwargs['organizationId'],
            client_id=kwargs.get('client_id'),
            domain=kwargs.get('domain', 'login'),
            api_version=kwargs.get('api_version', 63.0)
        )

    # Otherwise, use ip_filtering_non_service_login
    else:
        return ip_filtering_non_service_login(
            username=kwargs['username'],
            password=kwargs['password'],
            client_id=kwargs.get('client_id'),
            domain=kwargs.get('domain', 'login'),
            api_version=kwargs.get('api_version', 63.0)
        )
