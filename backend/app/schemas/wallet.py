from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.blockchain.addresses import normalize_address, supported_chain_ids
from app.blockchain.base import InvalidAddressError


class WalletCreate(BaseModel):
    """A public address to watch. Read-only: never send keys or seed phrases."""

    address: str = Field(min_length=1, max_length=128, examples=["0x0000000000000000000000000000000000000001"])
    chain: str = Field(examples=["ethereum"])
    label: str | None = Field(default=None, max_length=100)

    @field_validator("chain")
    @classmethod
    def _chain_supported(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in supported_chain_ids():
            raise ValueError(f"Unsupported chain. Supported: {', '.join(supported_chain_ids())}")
        return v

    @field_validator("label")
    @classmethod
    def _label_clean(cls, v: str | None) -> str | None:
        v = v.strip() if v else None
        return v or None

    @model_validator(mode="after")
    def _address_valid_for_chain(self) -> "WalletCreate":
        try:
            self.address = normalize_address(self.chain, self.address.strip())
        except InvalidAddressError as exc:
            raise ValueError(f"{exc.message} for chain '{self.chain}'") from None
        return self


class WalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    address: str
    chain: str
    label: str | None
    created_at: datetime


class WalletPage(BaseModel):
    items: list[WalletOut]
    total: int
    limit: int
    offset: int
