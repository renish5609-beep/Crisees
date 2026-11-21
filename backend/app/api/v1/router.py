from fastapi import APIRouter

from app.api.v1.routes import regions

api_router = APIRouter()
api_router.include_router(regions.router)
