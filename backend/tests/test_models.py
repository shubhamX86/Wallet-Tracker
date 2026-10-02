"""Schema-shape tests that need no database."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

import app.models  # noqa: F401
from app.db.base import Base


def test_tables_registered():
    assert {"users", "wallets"} <= set(Base.metadata.tables)


def test_users_email_unique_and_lowercase_check():
    users = Base.metadata.tables["users"]
    assert users.c.email.unique and users.c.email.index
    assert any(isinstance(c, CheckConstraint) for c in users.constraints)
    assert "password_hash" in users.c and "password" not in users.c


def test_wallet_unique_user_chain_address():
    wallets = Base.metadata.tables["wallets"]
    uniques = [c for c in wallets.constraints if isinstance(c, UniqueConstraint)]
    assert any([col.name for col in u.columns] == ["user_id", "chain", "address"] for u in uniques)


def test_wallet_fk_cascades_on_user_delete():
    wallets = Base.metadata.tables["wallets"]
    fk = next(c for c in wallets.constraints if isinstance(c, ForeignKeyConstraint))
    assert fk.ondelete == "CASCADE" and fk.elements[0].target_fullname == "users.id"


def test_no_secret_key_columns():
    cols = {c.name for c in Base.metadata.tables["wallets"].c}
    assert not cols & {"private_key", "seed_phrase", "mnemonic", "secret"}
