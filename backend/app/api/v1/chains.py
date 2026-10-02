"""GET /api/v1/chains — the network registry with honest implementation status."""
from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel

from app.chains.registry import CHAINS

router = APIRouter(tags=["chains"])


class ChainOut(BaseModel):
    id: str
    name: str
    family: str
    native_symbol: str
    evm_chain_id: int | None
    status: str
    planned_phase: int


@router.get("/chains", response_model=list[ChainOut])
async def list_chains() -> list[ChainOut]:
    return [ChainOut(**asdict(c)) for c in CHAINS]
