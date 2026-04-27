"""Tests for the retry transports in :mod:`sf_toolkit._retry`."""

from __future__ import annotations

from typing import Callable

import httpx
import pytest

from sf_toolkit import _retry
from sf_toolkit._retry import (
    DEFAULT_RETRY_METHODS,
    DEFAULT_RETRY_STATUSES,
    AsyncRetryTransport,
    RetryTransport,
    _compute_backoff,
    _parse_retry_after,
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Patch out sleeps so tests run instantly."""
    monkeypatch.setattr(_retry.time, "sleep", lambda _s: None)

    async def _async_noop(_s):
        return None

    monkeypatch.setattr(_retry.asyncio, "sleep", _async_noop)


# ---------------------------------------------------------------------------
# Helpers / pure-function tests
# ---------------------------------------------------------------------------


def test_parse_retry_after_numeric():
    assert _parse_retry_after("5") == 5.0
    assert _parse_retry_after("  2.5 ") == 2.5
    assert _parse_retry_after("0") == 0.0


def test_parse_retry_after_invalid():
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    assert _parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") is None


def test_parse_retry_after_negative_clamped():
    assert _parse_retry_after("-5") == 0.0


def test_compute_backoff_exponential_no_jitter():
    assert _compute_backoff(1, 0.5, 30.0, 0.0) == 0.5
    assert _compute_backoff(2, 0.5, 30.0, 0.0) == 1.0
    assert _compute_backoff(3, 0.5, 30.0, 0.0) == 2.0
    assert _compute_backoff(4, 0.5, 30.0, 0.0) == 4.0


def test_compute_backoff_max_clamps():
    assert _compute_backoff(20, 0.5, 5.0, 0.0) == 5.0


def test_compute_backoff_jitter_within_bounds():
    base = 0.5 * (2 ** (3 - 1))  # = 2.0
    for _ in range(20):
        delay = _compute_backoff(3, 0.5, 30.0, 0.5)
        assert base <= delay <= base + 0.5


# ---------------------------------------------------------------------------
# Sync transport tests
# ---------------------------------------------------------------------------


class _MockRetryTransport(RetryTransport):
    """RetryTransport subclass that delegates the inner request to a
    user-supplied handler, bypassing the real httpx connection pool."""

    def __init__(
        self,
        handler: Callable[[httpx.Request], httpx.Response],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._mock = httpx.MockTransport(handler)

    def _send(self, request: httpx.Request) -> httpx.Response:
        return self._mock.handle_request(request)

    # Avoid touching the real connection pool on enter/exit.
    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def _make_sync_transport(
    handler: Callable[[httpx.Request], httpx.Response],
    **kwargs,
) -> RetryTransport:
    return _MockRetryTransport(handler, **kwargs)


def test_sync_retries_on_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, text="ok")

    transport = _make_sync_transport(handler, max_retries=3, backoff_factor=0)
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 200
    assert calls["n"] == 3


def test_sync_retries_exhausted_returns_last_5xx(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    transport = _make_sync_transport(handler, max_retries=2, backoff_factor=0)
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 500
    # 1 initial + 2 retries
    assert calls["n"] == 3


def test_sync_retries_on_remote_protocol_error(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response.",
                request=request,
            )
        return httpx.Response(200, text="ok")

    transport = _make_sync_transport(handler, max_retries=3, backoff_factor=0)
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 200
    assert calls["n"] == 2


def test_sync_connection_error_exhausted_raises(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("nope", request=request)

    transport = _make_sync_transport(handler, max_retries=2, backoff_factor=0)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectError):
            client.get("https://example.test/x")

    assert calls["n"] == 3


def test_sync_does_not_retry_post_on_5xx(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    transport = _make_sync_transport(handler, max_retries=3, backoff_factor=0)
    with httpx.Client(transport=transport) as client:
        resp = client.post("https://example.test/x", json={})

    assert resp.status_code == 500
    assert calls["n"] == 1  # POST not in default retry methods


def test_sync_retries_post_on_connection_error(monkeypatch):
    """Connection-level errors are retried regardless of method, since the
    request body has not yet been delivered."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("nope", request=request)
        return httpx.Response(201, text="created")

    transport = _make_sync_transport(handler, max_retries=3, backoff_factor=0)
    with httpx.Client(transport=transport) as client:
        resp = client.post("https://example.test/x", json={})

    assert resp.status_code == 201
    assert calls["n"] == 2


def test_sync_does_not_retry_non_retry_status(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, text="missing")

    transport = _make_sync_transport(handler, max_retries=3, backoff_factor=0)
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 404
    assert calls["n"] == 1


def test_sync_max_retries_zero_disables_retry(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, text="busy")

    transport = _make_sync_transport(handler, max_retries=0, backoff_factor=0)
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 503
    assert calls["n"] == 1


def test_sync_respects_retry_after_header(monkeypatch):
    sleeps: list[float] = []

    def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(_retry.time, "sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"Retry-After": "7"}, text="busy")
        return httpx.Response(200, text="ok")

    transport = _make_sync_transport(
        handler, max_retries=3, backoff_factor=0.5, jitter=0.0, backoff_max=30.0
    )
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 200
    assert sleeps == [7.0]


def test_sync_retry_after_clamped_to_backoff_max(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(_retry.time, "sleep", lambda s: sleeps.append(s))

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"Retry-After": "9999"}, text="busy")
        return httpx.Response(200, text="ok")

    transport = _make_sync_transport(
        handler,
        max_retries=3,
        backoff_factor=0.5,
        jitter=0.0,
        backoff_max=10.0,
    )
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 200
    assert sleeps == [10.0]


def test_sync_respect_retry_after_can_be_disabled(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(_retry.time, "sleep", lambda s: sleeps.append(s))

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"Retry-After": "100"}, text="busy")
        return httpx.Response(200, text="ok")

    transport = _make_sync_transport(
        handler,
        max_retries=3,
        backoff_factor=0.5,
        jitter=0.0,
        respect_retry_after=False,
    )
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 200
    # First retry uses backoff_factor * 2**0 = 0.5, ignoring Retry-After.
    assert sleeps == [0.5]


def test_sync_negative_max_retries_rejected():
    with pytest.raises(ValueError):
        RetryTransport(max_retries=-1)


def test_sync_custom_retry_statuses(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, text="ok")

    transport = _make_sync_transport(
        handler,
        max_retries=3,
        backoff_factor=0,
        retry_statuses={429, *DEFAULT_RETRY_STATUSES},
    )
    with httpx.Client(transport=transport) as client:
        resp = client.get("https://example.test/x")

    assert resp.status_code == 200
    assert calls["n"] == 2


def test_default_retry_methods_excludes_post():
    assert "POST" not in DEFAULT_RETRY_METHODS
    assert "GET" in DEFAULT_RETRY_METHODS


# ---------------------------------------------------------------------------
# Async transport tests
# ---------------------------------------------------------------------------


class _MockAsyncRetryTransport(AsyncRetryTransport):
    """AsyncRetryTransport subclass that routes inner requests through a
    user-supplied handler instead of the real connection pool."""

    def __init__(self, handler, **kwargs) -> None:
        super().__init__(**kwargs)
        self._mock = httpx.MockTransport(handler)

    async def _asend(self, request: httpx.Request) -> httpx.Response:
        return await self._mock.handle_async_request(request)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None


def _make_async_transport(handler, **kwargs) -> AsyncRetryTransport:
    return _MockAsyncRetryTransport(handler, **kwargs)


@pytest.mark.asyncio
async def test_async_retries_on_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(502, text="bad gw")
        return httpx.Response(200, text="ok")

    transport = _make_async_transport(handler, max_retries=3, backoff_factor=0)
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.get("https://example.test/x")

    assert resp.status_code == 200
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_async_retries_on_remote_protocol_error(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response.",
                request=request,
            )
        return httpx.Response(200, text="ok")

    transport = _make_async_transport(handler, max_retries=2, backoff_factor=0)
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.get("https://example.test/x")

    assert resp.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_async_exhaustion_raises(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadError("dropped", request=request)

    transport = _make_async_transport(handler, max_retries=2, backoff_factor=0)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.ReadError):
            await client.get("https://example.test/x")

    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_async_does_not_retry_post_on_5xx(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    transport = _make_async_transport(handler, max_retries=3, backoff_factor=0)
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.post("https://example.test/x", json={})

    assert resp.status_code == 500
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_async_respects_retry_after(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(_retry.asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"Retry-After": "3"}, text="busy")
        return httpx.Response(200, text="ok")

    transport = _make_async_transport(
        handler, max_retries=3, backoff_factor=0.5, jitter=0.0, backoff_max=30.0
    )
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.get("https://example.test/x")

    assert resp.status_code == 200
    assert sleeps == [3.0]
