from fastapi import APIRouter

from app.api.v1.routes.job_roles import router as job_roles_router

api_router = APIRouter()
api_router.include_router(job_roles_router)
