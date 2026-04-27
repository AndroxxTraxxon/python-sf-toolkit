"""HTTP transports that add retry behavior for transient failures.

Salesforce occasionally drops idle keep-alive connections without sending
a response, and also returns transient 5xx responses under load. ``httpx``'s
built-in transports only retry on ``ConnectError`` (failures to establish a
socket), so this module layers a more comprehensive retry policy on top.

The retry logic lives in the *transport* rather than in
:meth:`httpx.Client.request` so that **every** request issued through the
client is covered, including the OAuth login/refresh requests that
``SalesforceAuth`` issues internally via ``Client.send()``.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Iterable

import httpx

from .logger import getLogger

LOGGER = getLogger("retry")

#: Default HTTP status codes that should trigger a retry.
DEFAULT_RETRY_STATUSES: frozenset[int] = frozenset({500, 502, 503, 504})

#: Default HTTP methods considered safe to retry. ``POST`` is intentionally
#: excluded because retrying a POST after a dropped connection can produce
#: duplicate Salesforce records.
DEFAULT_RETRY_METHODS: frozenset[str] = frozenset(
    {"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "PATCH"}
)

#: ``httpx`` exception types that indicate a transient transport-level failure.
#: ``RemoteProtocolError`` is the httpx analogue of ``RemoteDisconnected`` /
#: "Connection aborted" from ``requests``/``urllib3``.
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value into a number of seconds.

    Only the delta-seconds form is honored; HTTP-date forms are ignored.
    """
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        return None
    return max(seconds, 0.0)


def _compute_backoff(
    attempt: int,
    backoff_factor: float,
    backoff_max: float,
    jitter: float,
) -> float:
    """Exponential backoff with optional jitter.

    ``attempt`` is 1-based: the delay before the first retry uses ``attempt=1``.
    """
    delay = backoff_factor * (2 ** (attempt - 1))
    if jitter:
        delay += random.random() * jitter
    return min(delay, backoff_max)


class _RetryConfig:
    """Shared configuration container for the sync/async retry transports."""

    __slots__ = (
        "max_retries",
        "backoff_factor",
        "backoff_max",
        "jitter",
        "retry_statuses",
        "retry_methods",
        "retryable_exceptions",
        "respect_retry_after",
    )

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        backoff_max: float = 30.0,
        jitter: float = 0.1,
        retry_statuses: Iterable[int] = DEFAULT_RETRY_STATUSES,
        retry_methods: Iterable[str] = DEFAULT_RETRY_METHODS,
        retryable_exceptions: tuple[type[BaseException], ...] = RETRYABLE_EXCEPTIONS,
        respect_retry_after: bool = True,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.backoff_max = backoff_max
        self.jitter = jitter
        self.retry_statuses = frozenset(retry_statuses)
        self.retry_methods = frozenset(m.upper() for m in retry_methods)
        self.retryable_exceptions = tuple(retryable_exceptions)
        self.respect_retry_after = respect_retry_after

    def should_retry_method(self, method: str) -> bool:
        return method.upper() in self.retry_methods

    def should_retry_status(self, status_code: int) -> bool:
        return status_code in self.retry_statuses

    def delay_for(self, attempt: int, response: httpx.Response | None) -> float:
        if (
            self.respect_retry_after
            and response is not None
            and (ra := _parse_retry_after(response.headers.get("Retry-After")))
            is not None
        ):
            return min(ra, self.backoff_max)
        return _compute_backoff(
            attempt, self.backoff_factor, self.backoff_max, self.jitter
        )


class RetryTransport(httpx.HTTPTransport):
    """Synchronous HTTP transport that retries transient failures.

    Retries are attempted when:

    * The wrapped transport raises one of :data:`RETRYABLE_EXCEPTIONS`, or
    * The response status is in ``retry_statuses`` **and** the request method
      is in ``retry_methods``.

    Connection-level exceptions are retried regardless of method, because they
    typically occur before the request body has been delivered.
    """

    def __init__(
        self,
        *args: Any,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        backoff_max: float = 30.0,
        jitter: float = 0.1,
        retry_statuses: Iterable[int] = DEFAULT_RETRY_STATUSES,
        retry_methods: Iterable[str] = DEFAULT_RETRY_METHODS,
        retryable_exceptions: tuple[type[BaseException], ...] = RETRYABLE_EXCEPTIONS,
        respect_retry_after: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._retry = _RetryConfig(
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            backoff_max=backoff_max,
            jitter=jitter,
            retry_statuses=retry_statuses,
            retry_methods=retry_methods,
            retryable_exceptions=retryable_exceptions,
            respect_retry_after=respect_retry_after,
        )

    def _send(self, request: httpx.Request) -> httpx.Response:
        """Dispatch the request to the wrapped transport.

        Exposed as a hook so tests can substitute behavior without having to
        monkeypatch :class:`httpx.HTTPTransport` itself (whose
        ``__enter__``/``__exit__`` rely on its real connection pool).
        """
        return super().handle_request(request)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        cfg = self._retry
        method = request.method
        attempt = 0
        while True:
            try:
                response = self._send(request)
            except cfg.retryable_exceptions as exc:
                if attempt >= cfg.max_retries:
                    raise
                attempt += 1
                delay = _compute_backoff(
                    attempt, cfg.backoff_factor, cfg.backoff_max, cfg.jitter
                )
                LOGGER.warning(
                    "Retrying %s %s after transport error %s"
                    " (attempt %d/%d, sleeping %.2fs)",
                    method,
                    request.url,
                    exc.__class__.__name__,
                    attempt,
                    cfg.max_retries,
                    delay,
                )
                if delay:
                    time.sleep(delay)
                continue

            if (
                cfg.should_retry_status(response.status_code)
                and cfg.should_retry_method(method)
                and attempt < cfg.max_retries
            ):
                attempt += 1
                delay = cfg.delay_for(attempt, response)
                LOGGER.warning(
                    "Retrying %s %s after HTTP %d (attempt %d/%d, sleeping %.2fs)",
                    method,
                    request.url,
                    response.status_code,
                    attempt,
                    cfg.max_retries,
                    delay,
                )
                # Drain and release the connection back to the pool before sleeping.
                response.close()
                if delay:
                    time.sleep(delay)
                continue

            return response


class AsyncRetryTransport(httpx.AsyncHTTPTransport):
    """Asynchronous counterpart to :class:`RetryTransport`."""

    def __init__(
        self,
        *args: Any,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        backoff_max: float = 30.0,
        jitter: float = 0.1,
        retry_statuses: Iterable[int] = DEFAULT_RETRY_STATUSES,
        retry_methods: Iterable[str] = DEFAULT_RETRY_METHODS,
        retryable_exceptions: tuple[type[BaseException], ...] = RETRYABLE_EXCEPTIONS,
        respect_retry_after: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._retry = _RetryConfig(
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            backoff_max=backoff_max,
            jitter=jitter,
            retry_statuses=retry_statuses,
            retry_methods=retry_methods,
            retryable_exceptions=retryable_exceptions,
            respect_retry_after=respect_retry_after,
        )

    async def _asend(self, request: httpx.Request) -> httpx.Response:
        """Dispatch the request to the wrapped transport. See
        :meth:`RetryTransport._send` for rationale."""
        return await super().handle_async_request(request)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        cfg = self._retry
        method = request.method
        attempt = 0
        while True:
            try:
                response = await self._asend(request)
            except cfg.retryable_exceptions as exc:
                if attempt >= cfg.max_retries:
                    raise
                attempt += 1
                delay = _compute_backoff(
                    attempt, cfg.backoff_factor, cfg.backoff_max, cfg.jitter
                )
                LOGGER.warning(
                    "Retrying %s %s after transport error %s"
                    " (attempt %d/%d, sleeping %.2fs)",
                    method,
                    request.url,
                    exc.__class__.__name__,
                    attempt,
                    cfg.max_retries,
                    delay,
                )
                if delay:
                    await asyncio.sleep(delay)
                continue

            if (
                cfg.should_retry_status(response.status_code)
                and cfg.should_retry_method(method)
                and attempt < cfg.max_retries
            ):
                attempt += 1
                delay = cfg.delay_for(attempt, response)
                LOGGER.warning(
                    "Retrying %s %s after HTTP %d (attempt %d/%d, sleeping %.2fs)",
                    method,
                    request.url,
                    response.status_code,
                    attempt,
                    cfg.max_retries,
                    delay,
                )
                await response.aclose()
                if delay:
                    await asyncio.sleep(delay)
                continue

            return response


__all__ = [
    "AsyncRetryTransport",
    "DEFAULT_RETRY_METHODS",
    "DEFAULT_RETRY_STATUSES",
    "RETRYABLE_EXCEPTIONS",
    "RetryTransport",
]
