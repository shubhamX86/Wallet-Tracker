import pytest
from sqlalchemy import text

from tests.test_auth_api import auth_headers

ETH = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
SOL = "So11111111111111111111111111111111111111112"
BTC = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
TRON = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
URL = "/api/v1/wallets/"


async def add(api, headers, address=ETH, chain="ethereum", label=None):
    body = {"address": address, "chain": chain}
    if label is not None:
        body["label"] = label
    return await api.post(URL, json=body, headers=headers)


@pytest.fixture
async def alice(api):
    return await auth_headers(api, "alice@example.com")


@pytest.fixture
async def bob(api):
    return await auth_headers(api, "bob@example.com")


# ------------------------------------------------------------------ create
async def test_add_wallet_normalizes_address_and_label(api, alice):
    r = await add(api, alice, ETH.lower(), "Ethereum", "  Whale Alpha  ")
    assert r.status_code == 201
    body = r.json()
    assert body["address"] == ETH and body["chain"] == "ethereum" and body["label"] == "Whale Alpha"
    assert not {"user_id", "private_key"} & body.keys()


@pytest.mark.parametrize(
    "chain,address",
    [("ethereum", ETH), ("bsc", ETH), ("solana", SOL), ("bitcoin", BTC), ("tron", TRON), ("sui", "0x" + "ab" * 32)],
)
async def test_add_wallet_on_several_chains(api, alice, chain, address):
    assert (await add(api, alice, address, chain)).status_code == 201


async def test_unsupported_chain_rejected(api, alice):
    r = await add(api, alice, ETH, "dogecoin")
    assert r.status_code == 422 and "Unsupported chain" in r.text


@pytest.mark.parametrize(
    "chain,address",
    [("ethereum", TRON), ("ethereum", SOL), ("ethereum", "0x1234"), ("solana", ETH),
     ("bitcoin", ETH), ("tron", BTC), ("sui", ETH), ("ethereum", "0x" + ETH[2:].swapcase())],
)
async def test_address_must_match_chain(api, alice, chain, address):
    r = await add(api, alice, address, chain)
    assert r.status_code == 422


@pytest.mark.parametrize("payload", [{}, {"address": ETH}, {"chain": "ethereum"}, {"address": "", "chain": "ethereum"}])
async def test_missing_fields_rejected(api, alice, payload):
    assert (await api.post(URL, json=payload, headers=alice)).status_code == 422


async def test_label_too_long_rejected(api, alice):
    assert (await add(api, alice, label="x" * 101)).status_code == 422


async def test_duplicate_wallet_conflict_including_case_variants(api, alice):
    assert (await add(api, alice, ETH)).status_code == 201
    assert (await add(api, alice, ETH)).status_code == 409
    assert (await add(api, alice, ETH.lower())).status_code == 409  # normalizes to the same address


async def test_same_address_allowed_on_other_chain_and_for_other_user(api, alice, bob):
    assert (await add(api, alice, ETH, "ethereum")).status_code == 201
    assert (await add(api, alice, ETH, "bsc")).status_code == 201
    assert (await add(api, bob, ETH, "ethereum")).status_code == 201


async def test_no_secret_fields_are_accepted_or_stored(api, alice, db):
    r = await api.post(URL, json={"address": ETH, "chain": "ethereum", "private_key": "0xdeadbeef"}, headers=alice)
    assert r.status_code == 201 and "private_key" not in r.text
    with db.connect() as c:
        cols = {row[0] for row in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='wallets'"))}
    assert not cols & {"private_key", "seed_phrase", "mnemonic", "secret"}


# ------------------------------------------------------------------ list / filter / paginate
async def test_list_returns_only_own_wallets_newest_first(api, alice, bob):
    await add(api, alice, ETH, "ethereum")
    await add(api, alice, SOL, "solana")
    await add(api, bob, BTC, "bitcoin")
    page = (await api.get(URL, headers=alice)).json()
    assert page["total"] == 2 and [w["chain"] for w in page["items"]] == ["solana", "ethereum"]
    assert (await api.get(URL, headers=bob)).json()["total"] == 1


async def test_pagination_is_stable_and_complete(api, alice):
    for i in range(5):
        await add(api, alice, "0x" + f"{i + 1:040x}", "ethereum")
    p1 = (await api.get(URL, params={"limit": 2, "offset": 0}, headers=alice)).json()
    p2 = (await api.get(URL, params={"limit": 2, "offset": 2}, headers=alice)).json()
    p3 = (await api.get(URL, params={"limit": 2, "offset": 4}, headers=alice)).json()
    ids = [w["id"] for p in (p1, p2, p3) for w in p["items"]]
    assert p1["total"] == 5 and len(ids) == 5 and len(set(ids)) == 5 and ids == sorted(ids, reverse=True)
    assert (await api.get(URL, params={"offset": 99}, headers=alice)).json()["items"] == []


async def test_chain_filter(api, alice):
    await add(api, alice, ETH, "ethereum")
    await add(api, alice, SOL, "solana")
    page = (await api.get(URL, params={"chain": "solana"}, headers=alice)).json()
    assert page["total"] == 1 and page["items"][0]["address"] == SOL


@pytest.mark.parametrize("params", [{"chain": "dogecoin"}, {"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "x"}])
async def test_invalid_query_params_rejected(api, alice, params):
    assert (await api.get(URL, params=params, headers=alice)).status_code == 422


# ------------------------------------------------------------------ get / delete / isolation
async def test_get_own_wallet(api, alice):
    wid = (await add(api, alice)).json()["id"]
    r = await api.get(f"{URL}{wid}", headers=alice)
    assert r.status_code == 200 and r.json()["address"] == ETH


async def test_other_users_wallet_is_indistinguishable_from_missing(api, alice, bob):
    wid = (await add(api, alice)).json()["id"]
    theirs = await api.get(f"{URL}{wid}", headers=bob)
    missing = await api.get(f"{URL}999999", headers=bob)
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()


async def test_delete_own_wallet(api, alice):
    wid = (await add(api, alice)).json()["id"]
    assert (await api.delete(f"{URL}{wid}", headers=alice)).status_code == 204
    assert (await api.get(f"{URL}{wid}", headers=alice)).status_code == 404
    assert (await api.delete(f"{URL}{wid}", headers=alice)).status_code == 404


async def test_cannot_delete_other_users_wallet(api, alice, bob):
    wid = (await add(api, alice)).json()["id"]
    assert (await api.delete(f"{URL}{wid}", headers=bob)).status_code == 404
    assert (await api.get(f"{URL}{wid}", headers=alice)).status_code == 200  # still there


async def test_deleting_a_wallet_removes_its_transactions(api, alice, db):
    wid = (await add(api, alice)).json()["id"]
    with db.begin() as c:
        c.execute(text("INSERT INTO transactions (wallet_id, chain, tx_hash) VALUES (:w, 'ethereum', '0xh')"), {"w": wid})
        c.execute(text("INSERT INTO sync_checkpoints (wallet_id, chain) VALUES (:w, 'ethereum')"), {"w": wid})
    await api.delete(f"{URL}{wid}", headers=alice)
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM transactions")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM sync_checkpoints")).scalar() == 0


@pytest.mark.parametrize("method,path", [("get", URL), ("get", f"{URL}1"), ("post", URL), ("delete", f"{URL}1")])
async def test_all_wallet_routes_require_auth(api, method, path):
    kwargs = {"json": {"address": ETH, "chain": "ethereum"}} if method == "post" else {}
    assert (await getattr(api, method)(path, **kwargs)).status_code == 401


async def test_wallet_routes_reject_a_forged_token(api):
    r = await api.get(URL, headers={"Authorization": "Bearer forged.token.value"})
    assert r.status_code == 401
