from fastapi import APIRouter

from app.api.v1 import auth, chains, health, wallets

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(chains.router)
api_router.include_router(auth.router)
api_router.include_router(wallets.router)
