"""Classification data model: constraints, versioning, and model/migration agreement."""
import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classification.types import Basis, EvidenceStrength, TxLabel
from app.models import TransactionClassification
from tests.conftest import alembic_config


def _wallet(conn, email="a@example.com", address="0xabc") -> int:
    uid = conn.execute(
        text("INSERT INTO users (email, password_hash) VALUES (:e, 'x') RETURNING id"), {"e": email}
    ).scalar()
    return conn.execute(
        text("INSERT INTO wallets (user_id, address, chain) VALUES (:u, :a, 'ethereum') RETURNING id"),
        {"u": uid, "a": address},
    ).scalar()


def _cls(conn, wallet_id, tx="0xh1", version="evm-1", label="native_transfer",
         strength="strong", basis="observed", method="evm_native_value"):
    conn.execute(
        text(
            "INSERT INTO transaction_classifications "
            "(wallet_id, chain, tx_hash, rule_version, label, evidence_strength, basis, detection_method) "
            "VALUES (:w, 'ethereum', :tx, :v, :l, :s, :b, :m)"
        ),
        {"w": wallet_id, "tx": tx, "v": version, "l": label, "s": strength, "b": basis, "m": method},
    )


def test_model_matches_migrations_no_drift(migrated_db_url):
    """`alembic check` raises if the ORM models differ from what the migrations produce."""
    command.check(alembic_config(migrated_db_url))


def test_defaults_applied(db):
    with db.begin() as c:
        w = _wallet(c)
        _cls(c, w)
        row = c.execute(
            text("SELECT evidence, uncertainty_notes, transfer_indexes, assets, classified_at, tx_timestamp "
                 "FROM transaction_classifications")
        ).one()
    assert row.evidence == [] and row.uncertainty_notes == [] and row.transfer_indexes == []
    assert row.assets is None and row.tx_timestamp is None  # unknown stays NULL
    assert row.classified_at is not None


@pytest.mark.parametrize("label", [m.value for m in TxLabel if m is not TxLabel.UNKNOWN])
def test_every_real_label_accepted_with_evidence(db, label):
    with db.begin() as c:
        _cls(c, _wallet(c), label=label, strength="weak", basis="inferred")


def test_unknown_accepted_only_with_no_evidence(db):
    with db.begin() as c:
        w = _wallet(c)
        _cls(c, w, label="unknown", strength="none", basis="inferred", method="no_rule_matched")
    for strength in ("strong", "moderate", "weak"):
        with pytest.raises(IntegrityError):
            with db.begin() as c:
                _cls(c, w, tx=f"0x{strength}", label="unknown", strength=strength)


@pytest.mark.parametrize("strength", ["strong", "moderate", "weak"])
def test_real_label_cannot_claim_no_evidence(db, strength):
    with db.begin() as c:
        w = _wallet(c)
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            _cls(c, w, label="swap", strength="none")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"label": "buy"},  # never a valid label: we don't claim buys/sells
        {"label": "sell"},
        {"strength": "certain"},
        {"basis": "guessed"},
    ],
)
def test_invalid_vocabulary_rejected(db, kwargs):
    with db.begin() as c:
        w = _wallet(c)
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            _cls(c, w, **kwargs)


def test_same_rule_version_cannot_duplicate(db):
    with db.begin() as c:
        w = _wallet(c)
        _cls(c, w)
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            _cls(c, w)


def test_new_rule_version_keeps_history(db):
    with db.begin() as c:
        w = _wallet(c)
        _cls(c, w, version="evm-1", label="contract_interaction", strength="weak", basis="inferred")
        _cls(c, w, version="evm-2", label="swap", strength="moderate", basis="inferred")
        rows = c.execute(
            text("SELECT rule_version, label FROM transaction_classifications ORDER BY rule_version")
        ).all()
    assert [tuple(r) for r in rows] == [("evm-1", "contract_interaction"), ("evm-2", "swap")]


def test_same_tx_for_different_wallets_allowed(db):
    with db.begin() as c:
        _cls(c, _wallet(c, "a@example.com", "0xa"))
        _cls(c, _wallet(c, "b@example.com", "0xb"))


def test_wallet_required_and_delete_cascades(db):
    with pytest.raises(IntegrityError):
        with db.begin() as c:
            _cls(c, 424242)
    with db.begin() as c:
        w = _wallet(c)
        _cls(c, w)
        c.execute(text("DELETE FROM wallets WHERE id = :w"), {"w": w})
        assert c.execute(text("SELECT count(*) FROM transaction_classifications")).scalar() == 0


def test_orm_roundtrip_with_structured_evidence(db):
    """The ORM model must read/write what the migration created (arrays + JSONB)."""
    with db.begin() as c:
        w = _wallet(c)
    evidence = [{"type": "erc20_transfer_log", "log_index": 3, "token": "0xtoken", "value_raw": "1000"}]
    with Session(db) as s:
        s.add(
            TransactionClassification(
                wallet_id=w, chain="ethereum", tx_hash="0xh1", transfer_indexes=[0, 3],
                label=TxLabel.TOKEN_TRANSFER.value, basis=Basis.OBSERVED.value,
                evidence_strength=EvidenceStrength.STRONG.value, detection_method="evm_erc20_transfer_log",
                rule_version="evm-1", evidence=evidence, assets=[{"token": "0xtoken", "raw": "1000"}],
                uncertainty_notes=["token price unavailable"],
            )
        )
        s.commit()
        got = s.scalars(select(TransactionClassification)).one()
        assert got.transfer_indexes == [0, 3] and got.evidence == evidence
        assert got.uncertainty_notes == ["token price unavailable"] and got.classified_at is not None


def test_indexes_exist(db):
    names = {i["name"] for i in inspect(db).get_indexes("transaction_classifications")}
    assert {"ix_tx_class_wallet_id_tx_timestamp", "ix_tx_class_label", "ix_tx_class_chain_tx_hash"} <= names


def test_vocabulary_has_all_requested_labels():
    assert {m.value for m in TxLabel} == {
        "native_transfer", "token_transfer", "swap", "bridge_transfer", "exchange_deposit",
        "exchange_withdrawal", "contract_interaction", "liquidity_add", "liquidity_remove",
        "mint", "burn", "nft_transfer", "unknown",
    }
