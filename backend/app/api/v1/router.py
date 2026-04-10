from fastapi import APIRouter

from app.api.v1.routes.candidates import router as candidates_router
from app.api.v1.routes.job_descriptions import router as job_descriptions_router
from app.api.v1.routes.job_roles import router as job_roles_router
from app.api.v1.routes.resumes import router as resumes_router

api_router = APIRouter()
api_router.include_router(job_roles_router)
api_router.include_router(resumes_router)
api_router.include_router(job_descriptions_router)
api_router.include_router(candidates_router)
