from fastapi import APIRouter

from finn_api.api.copilot import router as copilot_router
from finn_api.api.health import router as health_router
from finn_api.api.network import router as network_router
from finn_api.api.push import router as push_router
from finn_api.api.research import router as research_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(copilot_router)
api_router.include_router(push_router)
api_router.include_router(network_router)
api_router.include_router(research_router)
