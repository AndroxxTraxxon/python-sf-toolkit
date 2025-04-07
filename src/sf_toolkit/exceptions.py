"""All exceptions for Salesforce Toolkit"""

import httpx


class SalesforceError(Exception):
    """Base Salesforce API exception"""

    message = "Unknown error occurred for {url_path}. Response content: {content}"

    def __init__(self, response: httpx.Response, resource_name: str):
        """Initialize the SalesforceError exception

        SalesforceError is the base class of exceptions in salesforce-toolkit

        Args:
            url_path: Salesforce URL that was called
            status: Status code of the error response
            resource_name: Name of the Salesforce resource being queried
            content: content of the response
        """

        self.url_path = response.url.path
        self.status_code = response.status_code
        self.status_description = response.reason_phrase
        self.resource_name = resource_name
        self.content = response.text
        self.method = response.request.method
        super().__init__(str(self))

    def __str__(self):
        return self.message.format(
            status_code=self.status_code, url_path=self.url_path, content=self.content
        )

    def __repr__(self):
        return f"{type(self).__name__}: {str(self)}"

    def __unicode__(self):
        return self.__str__()


class SalesforceMoreThanOneRecord(SalesforceError):
    """
    Error Code: 300
    The value returned when an external ID exists in more than one record. The
    response body contains the list of matching records.
    """

    message = "({status_code}) More than one record for {url_path}. Response content: {content}"


class SalesforceRecordNotModifiedSince(SalesforceError):
    """
    Error Code: 304
    The request content hasn’t changed since a specified date and time.
    The date and time is provided in a If-Modified-Since header.
    """

    def __init__(self, response: httpx.Response, resource_name: str):
        self.if_modified_since = response.headers.get("If-Modified-Since")
        super().__init__(response, resource_name)

    def __str__(self):
        return (
            f"({self.status_code}) Content not modified since {self.if_modified_since} for {self.url_path}. "
            f"Response content: {self.content}"
        )


class SalesforceMalformedRequest(SalesforceError):
    """
    Error Code: 400
    The request couldn't be understood, usually because the JSON or XML body
    contains an error.
    """

    message = (
        "({status_code}) Malformed request {url_path}. Response content: {content}"
    )


class SalesforceExpiredSession(SalesforceError):
    """
    Error Code: 401
    The session ID or OAuth token used has expired or is invalid. The response
    body contains the message and errorCode.
    """

    message = (
        "({status_code}) Expired session for {url_path}. Response content: {content}"
    )


class SalesforceRefusedRequest(SalesforceError):
    """
    Error Code: 403
    The request has been refused. Verify that the logged-in user has
    appropriate permissions.
    """

    message = (
        "({status_code}) Request refused for {url_path}. Response content: {content}"
    )


class SalesforceResourceNotFound(SalesforceError):
    """
    Error Code: 404
    The requested resource couldn't be found. Check the URI for errors, and
    verify that there are no sharing issues.
    """

    def __str__(self):
        return (
            f"({self.status_code}) "
            f"Resource {self.resource_name} Not Found at {self.url_path}. "
            f"Response content: {self.content}"
        )


class SalesforceMethodNotAllowedForResource(SalesforceError):
    """
    Error Code: 405
    The method specified in the Request-Line isn't allowed for
    the resource specified in the URI.
    """

    message = "({status_code}) HTTP Method Not Allowed for {url_path}. Response content: {content}"


class SalesforceApiVersionIncompatible(SalesforceError):
    """
    Error Code: 409

    The request couldn't be completed due to a conflict with the current state
    of the resource. Check that the API version is compatible with the resource
    you're requesting.
    """

    message = "({status_code}) API Version incompatible for {url_path}. Response content: {content}"


class SalesforceResourceRemoved(SalesforceError):
    """
    Error Code: 410

    The requested resource has been retired or removed.
    Delete or update any references to the resource.
    """

    message = (
        "({status_code}) Resource removed from {url_path}. Response content: {content}"
    )


class SalesforceInvalidHeaderPreconditions(SalesforceError):
    """
    Error Code: 412

    The request wasn't executed because one or more of the preconditions that
    the client specified in the request headers wasn't satisfied.
    For example, the request includes an If-Unmodified-Since header,
    but the data was modified after the specified date.
    """

    message = "({status_code}) Invalid Header Preconditions for {url_path}. Response content: {content}"


class SalesforceUriLimitExceeded(SalesforceError):
    """
    Error Code: 414

    The length of the URI exceeds the 16,384-byte limit.
    """

    message = (
        "({status_code}) URI Limit Exceeded for {url_path}. Response content: {content}"
    )


class SalesforceUnsupportedFormat(SalesforceError):
    """
    Error Code: 415

    The entity in the request is in a format that's
    not supported by the specified method.
    """

    message = "({status_code}) Unsupported Content Format for {url_path}. Response content: {content}"


class SalesforceEdgeRoutingUnavailable(SalesforceError):
    """
    Error Code: 420

    Salesforce Edge doesn't have routing information available for this request host.
    Contact Salesforce Customer Support.
    """

    message = (
        "({status_code}) Salesforce Edge Routing Unavailable for {url_path}. "
        "Response content: {content}"
    )


class SalesforceMissingConditionalHeader(SalesforceError):
    """
    Error Code: 428
    The request wasn't executed because it wasn't conditional.
    Add one of the Conditional Request Headers, such as If-Match,
    to the request and resubmit it.
    """

    message = "({status_code}) Conditional Header Missing for {url_path}. Response content: {content}"


class SalesforceHeaderLimitExceeded(SalesforceError):
    """
    Error Code: 431

    The combined length of the URI and headers exceeds the 16,384-byte limit.
    """

    message = "({status_code}) URI and Header exceeded 16kb limit for {url_path}.Response content: {content}"


class SalesforceServerError(SalesforceError):
    """
    Error Code: 500

    An error has occurred within Lightning Platform,
    so the request couldn't be completed.
    Contact Salesforce Customer Support.
    """

    message = "({status_code}) Salesforce Server Error for {url_path}. Response content: {content}"


class SalesforceEdgeCommFailure(SalesforceError):
    """
    Error Code: 502

    Salesforce Edge wasn't able to communicate successfully
    with the Salesforce instance.
    """

    message = (
        "({status_code}) Salesforce Edge Communication Failure for {url_path}. "
        "Response content: {content}"
    )


class SalesforceServerUnavailable(SalesforceError):
    """
    Error Code: 503

    The server is unavailable to handle the request.
    Typically this issue occurs if the server is down
    for maintenance or is overloaded.
    """

    message = "({status_code}) Salesforce Server Unavailable for {url_path}. Response content: {content}"


class SalesforceAuthenticationFailed(Exception):
    """
    Thrown to indicate that authentication with Salesforce failed.
    """

    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(str(self))

    def __str__(self):
        return f"{self.code}: {self.message}"


class SalesforceGeneralError(SalesforceError):
    """
    A non-specific Salesforce error.
    """

    def __str__(self):
        return (
            f"{self.status_description} ({self.status_code}) error occurred "
            f"with {self.method.upper()} to "
            f"{self.url_path[:255]}{'...' if len(self.url_path) > 255 else ''}"
            f"\n\n{self.content}"
        )


class SalesforceOperationError(Exception):
    """Base error for Bulk API 2.0 operations"""


class SalesforceBulkV2LoadError(SalesforceOperationError):
    """
    Error occurred during bulk 2.0 load
    """


class SalesforceBulkV2ExtractError(SalesforceOperationError):
    """
    Error occurred during bulk 2.0 extract
    """


_error_code_exception_map: dict[int, type[SalesforceError]] = {
    300: SalesforceMoreThanOneRecord,
    304: SalesforceRecordNotModifiedSince,
    400: SalesforceMalformedRequest,
    401: SalesforceExpiredSession,
    403: SalesforceRefusedRequest,
    404: SalesforceResourceNotFound,
    405: SalesforceMethodNotAllowedForResource,
    409: SalesforceApiVersionIncompatible,
    410: SalesforceResourceRemoved,
    412: SalesforceInvalidHeaderPreconditions,
    414: SalesforceUriLimitExceeded,
    415: SalesforceUnsupportedFormat,
    420: SalesforceEdgeRoutingUnavailable,
    428: SalesforceMissingConditionalHeader,
    431: SalesforceHeaderLimitExceeded,
    500: SalesforceServerError,
    502: SalesforceEdgeCommFailure,
    503: SalesforceServerUnavailable,
}


def raise_for_status(response: httpx.Response, name: str = ""):
    if response.is_success:
        return
    raise _error_code_exception_map.get(response.status_code, SalesforceGeneralError)(
        response, name
    )
