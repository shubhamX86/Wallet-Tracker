"""DB-level tests for transactions/sync_checkpoints against an isolated migrated database."""
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import alembic_config, drop_database, recreate_database

UINT256_MAX = 2**256 - 1


def _seed_wallet(conn, email="a@example.com", address="0xabc", chain="ethereum") -> int:
    uid = conn.execute(
        text("INSERT INTO users (email, password_hash) VALUES (:e, 'x') RETURNING id"), {"e": email}
    ).scalar()
    return conn.execute(
        text("INSERT INTO wallets (user_id, address, chain) VALUES (:u, :a, :c) RETURNING id"),
        {"u": uid, "a": address, "c": chain},
    ).scalar()


def _tx(conn, wallet_id, h="0xh1", idx=0, **extra):
    cols = {"wallet_id": wallet_id, "chain": "ethereum", "tx_hash": h, "transfer_index": idx, **extra}
    names = ", ".join(cols)
    params = ", ".join(f":{k}" for k in cols)
    conn.execute(text(f"INSERT INTO transactions ({names}) VALUES ({params})"), cols)


def test_duplicate_transfer_rejected(db):
    with db.begin() as c:
        w = _seed_wallet(c)
        _tx(c, w)
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            _tx(c, w)


def test_same_hash_different_transfer_index_allowed(db):
    with db.begin() as c:
        w = _seed_wallet(c)
        _tx(c, w, idx=0)
        _tx(c, w, idx=1)  # e.g. an ERC-20 Transfer log in the same tx
        n = c.execute(text("SELECT count(*) FROM transactions")).scalar()
    assert n == 2


def test_same_hash_for_different_wallets_allowed(db):
    with db.begin() as c:
        w1 = _seed_wallet(c, "a@example.com", "0xabc")
        w2 = _seed_wallet(c, "b@example.com", "0xdef")
        _tx(c, w1)
        _tx(c, w2)


def test_invalid_status_rejected(db):
    with db.begin() as c:
        w = _seed_wallet(c)
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            _tx(c, w, status="sell")


def test_negative_transfer_index_rejected(db):
    with db.begin() as c:
        w = _seed_wallet(c)
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            _tx(c, w, idx=-1)


def test_foreign_key_requires_wallet(db):
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            _tx(c, 999999)


def test_uint256_amount_roundtrips_exactly(db):
    with db.begin() as c:
        w = _seed_wallet(c)
        _tx(c, w, value=UINT256_MAX, fee=1)
        v, f = c.execute(text("SELECT value, fee FROM transactions")).one()
    assert v == Decimal(UINT256_MAX) and f == Decimal(1)


def test_unknown_values_are_null_not_zero(db):
    with db.begin() as c:
        w = _seed_wallet(c)
        _tx(c, w)
        row = c.execute(text("SELECT value, fee, status, timestamp, block_number FROM transactions")).one()
    assert all(x is None for x in row)


def test_checkpoint_one_per_wallet_and_defaults(db):
    with db.begin() as c:
        w = _seed_wallet(c)
        c.execute(text("INSERT INTO sync_checkpoints (wallet_id, chain) VALUES (:w, 'ethereum')"), {"w": w})
        status = c.execute(text("SELECT status FROM sync_checkpoints")).scalar()
    assert status == "pending"
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            c.execute(text("INSERT INTO sync_checkpoints (wallet_id, chain) VALUES (:w, 'ethereum')"), {"w": w})


def test_checkpoint_invalid_status_rejected(db):
    with db.begin() as c:
        w = _seed_wallet(c)
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            c.execute(
                text("INSERT INTO sync_checkpoints (wallet_id, chain, status) VALUES (:w, 'ethereum', 'bogus')"),
                {"w": w},
            )


def test_deleting_wallet_cascades(db):
    with db.begin() as c:
        w = _seed_wallet(c)
        _tx(c, w)
        c.execute(text("INSERT INTO sync_checkpoints (wallet_id, chain) VALUES (:w, 'ethereum')"), {"w": w})
        c.execute(text("DELETE FROM wallets WHERE id = :w"), {"w": w})
        assert c.execute(text("SELECT count(*) FROM transactions")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM sync_checkpoints")).scalar() == 0


def test_deleting_user_cascades_to_transactions(db):
    with db.begin() as c:
        w = _seed_wallet(c)
        _tx(c, w)
        c.execute(text("DELETE FROM users"))
        assert c.execute(text("SELECT count(*) FROM transactions")).scalar() == 0


def test_expected_indexes_exist(db):
    names = {i["name"] for i in inspect(db).get_indexes("transactions")}
    assert {
        "ix_transactions_wallet_id_timestamp",
        "ix_transactions_wallet_id_block_number",
        "ix_transactions_chain_tx_hash",
    } <= names


def test_migration_downgrade_and_upgrade_roundtrip():
    url = recreate_database("whale_mig_test")
    try:
        cfg = alembic_config(url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        assert {"users", "wallets", "transactions", "sync_checkpoints"} <= set(inspect(engine).get_table_names())

        command.downgrade(cfg, "0002")
        assert "transaction_classifications" not in set(inspect(engine).get_table_names())
        assert "transactions" in set(inspect(engine).get_table_names())

        command.downgrade(cfg, "0001")
        tables = set(inspect(engine).get_table_names())
        assert "transactions" not in tables and "sync_checkpoints" not in tables
        assert {"users", "wallets"} <= tables

        command.downgrade(cfg, "base")
        assert not {"users", "wallets"} & set(inspect(engine).get_table_names())

        command.upgrade(cfg, "head")
        assert "transactions" in set(inspect(engine).get_table_names())
        engine.dispose()
    finally:
        drop_database("whale_mig_test")
