from fastapi import APIRouter

from app.api.v1.citizens import router as citizens_router
from app.api.v1.schemes import router as schemes_router
from app.api.v1.eligibility import router as eligibility_router
from app.api.v1.recommendations import router as recommendations_router

api_router = APIRouter()

api_router.include_router(citizens_router, prefix="/citizens", tags=["Citizens"])
api_router.include_router(schemes_router, prefix="/schemes", tags=["Schemes"])
api_router.include_router(eligibility_router, prefix="/eligibility", tags=["Eligibility"])
api_router.include_router(recommendations_router, prefix="/recommendations", tags=["Recommendations"])
