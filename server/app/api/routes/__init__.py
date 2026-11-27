"""Every route, mounted under ``/api``."""

from fastapi import APIRouter

from app.api.routes import chat, health, live, network, patterns, trains

api_router = APIRouter(prefix="/api")
for module in (health, network, chat, trains, live, patterns):
    api_router.include_router(module.router)
