import httpx
import pytest

from app.blockchain.base import ProviderResponseError, ProviderUnavailableError, RateLimitedError
from app.blockchain.rpc import JsonRpcClient

SECRET_URL = "https://node.example.com/v1/SUPERSECRETKEY"


async def _nosleep(_):  # keeps retry tests instant
    pass


def client(handler, **kw) -> JsonRpcClient:
    return JsonRpcClient(
        SECRET_URL, label="bnb", transport=httpx.MockTransport(handler), sleep=_nosleep, **kw
    )


def ok(result):
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})


async def test_success_returns_result():
    assert await client(lambda r: ok("0x10")).call("eth_blockNumber") == "0x10"


async def test_null_result_is_returned_not_an_error():
    assert await client(lambda r: ok(None)).call("eth_getTransactionByHash", ["0x"]) is None


async def test_rate_limit_http_429_retried_then_raised():
    calls = []

    def h(r):
        calls.append(1)
        return httpx.Response(429)

    with pytest.raises(RateLimitedError):
        await client(h, max_retries=2).call("eth_blockNumber")
    assert len(calls) == 3  # 1 try + 2 bounded retries


async def test_rate_limit_via_rpc_error_code():
    h = lambda r: httpx.Response(200, json={"error": {"code": -32005, "message": "x"}})  # noqa: E731
    with pytest.raises(RateLimitedError):
        await client(h, max_retries=0).call("m")


async def test_timeout_retried_then_unavailable():
    calls = []

    def h(r):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ProviderUnavailableError):
        await client(h, max_retries=2).call("m")
    assert len(calls) == 3


async def test_recovers_after_transient_failure():
    seq = iter([httpx.Response(503), ok("0x1")])
    assert await client(lambda r: next(seq), max_retries=2).call("m") == "0x1"


async def test_backoff_is_exponential():
    delays = []

    async def rec(d):
        delays.append(d)

    c = JsonRpcClient(
        SECRET_URL, label="bnb", backoff=0.5, max_retries=3, sleep=rec,
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
    )
    with pytest.raises(ProviderUnavailableError):
        await c.call("m")
    assert delays == [0.5, 1.0, 2.0]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403),  # rejected: do not retry
        httpx.Response(200, content=b"<html>not json</html>"),
        httpx.Response(200, json=["not", "a", "dict"]),
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 1}),  # no result
        httpx.Response(200, json={"error": {"code": -32000, "message": "boom"}}),
    ],
)
async def test_invalid_responses_raise_and_are_not_retried(response):
    calls = []

    def h(r):
        calls.append(1)
        return response

    with pytest.raises(ProviderResponseError):
        await client(h, max_retries=2).call("m")
    assert len(calls) == 1


async def test_errors_never_leak_url_or_key():
    echo = lambda r: httpx.Response(  # noqa: E731
        200, json={"error": {"code": -32000, "message": f"bad request to {SECRET_URL}"}}
    )
    for h in (echo, lambda r: httpx.Response(500), lambda r: (_ for _ in ()).throw(httpx.ConnectError(SECRET_URL))):
        with pytest.raises(Exception) as ei:
            await client(h, max_retries=0).call("m")
        assert "SUPERSECRETKEY" not in str(ei.value) and "example.com" not in str(ei.value)


def test_rejects_non_http_url():
    with pytest.raises(ValueError):
        JsonRpcClient("file:///etc/passwd", label="x")
    with pytest.raises(ValueError):
        JsonRpcClient("ftp://host", label="x")
