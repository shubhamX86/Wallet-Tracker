"""Import every model here so Base.metadata (and Alembic autogenerate) sees them."""
from app.models.sync_checkpoint import SyncCheckpoint
from app.models.transaction import Transaction
from app.models.transaction_classification import TransactionClassification
from app.models.user import User
from app.models.wallet import Wallet

__all__ = ["SyncCheckpoint", "Transaction", "TransactionClassification", "User", "Wallet"]
