"""Minimal JSON-RPC 2.0 client over HTTP with failure classification and bounded retries.

- The URL (which may embed an API key) is held privately and never appears in errors or logs.
- Retries only transient failures (timeouts, connection errors, 5xx, rate limits) with
  exponential backoff; invalid requests / malformed responses are never retried.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.blockchain.base import (
    ProviderResponseError, ProviderUnavailableError, RateLimitedError,
)
from app.core.logging import get_logger

log = get_logger("whale.rpc")

# JSON-RPC error codes providers commonly use for throttling.
_RATE_LIMIT_CODES = {-32005, 429}
_RATE_LIMIT_HINTS = ("rate limit", "too many requests", "limit exceeded", "throttl")


class JsonRpcClient:
    def __init__(
        self,
        url: str,
        *,
        label: str,
        timeout: float = 10.0,
        max_retries: int = 2,
        backoff: float = 0.25,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("RPC URL must be http(s)")
        self._url = url
        self.label = label  # safe, human-readable provider name (e.g. "bnb")
        self._max_retries = max(0, max_retries)
        self._backoff = backoff
        self._sleep = sleep
        self._next_id = 0
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        """Return the JSON-RPC `result` (may legitimately be None, e.g. unknown tx hash)."""
        for attempt in range(self._max_retries + 1):
            try:
                return await self._once(method, params or [])
            except (ProviderUnavailableError, RateLimitedError) as exc:
                if attempt == self._max_retries:
                    raise
                log.warning(
                    "rpc_retry", provider=self.label, method=method, attempt=attempt + 1,
                    reason=type(exc).__name__,
                )
                await self._sleep(self._backoff * (2**attempt))
        raise AssertionError("unreachable")  # pragma: no cover

    async def _once(self, method: str, params: list[Any]) -> Any:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        try:
            resp = await self._http.post(self._url, json=payload)
        except httpx.TimeoutException:
            raise ProviderUnavailableError(f"{self.label} provider timed out") from None
        except httpx.HTTPError:
            raise ProviderUnavailableError(f"{self.label} provider unreachable") from None

        if resp.status_code == 429:
            raise RateLimitedError(f"{self.label} provider rate limit reached")
        if resp.status_code >= 500:
            raise ProviderUnavailableError(f"{self.label} provider error (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise ProviderResponseError(f"{self.label} provider rejected the request (HTTP {resp.status_code})")

        try:
            body = resp.json()
        except ValueError:
            raise ProviderResponseError(f"{self.label} provider returned malformed JSON") from None
        if not isinstance(body, dict):
            raise ProviderResponseError(f"{self.label} provider returned an unexpected response")

        err = body.get("error")
        if err is not None:
            code = err.get("code") if isinstance(err, dict) else None
            msg = str(err.get("message", "")).lower() if isinstance(err, dict) else ""
            if code in _RATE_LIMIT_CODES or any(h in msg for h in _RATE_LIMIT_HINTS):
                raise RateLimitedError(f"{self.label} provider rate limit reached")
            # Provider message is deliberately dropped: it may echo URLs/keys.
            raise ProviderResponseError(f"{self.label} provider returned an RPC error (code {code})")
        if "result" not in body:
            raise ProviderResponseError(f"{self.label} provider response had no result")
        return body["result"]

    async def aclose(self) -> None:
        await self._http.aclose()
