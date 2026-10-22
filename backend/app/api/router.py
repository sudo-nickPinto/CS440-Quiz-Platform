from fastapi import APIRouter

from app.api.routes.class_dashboard import router as class_dashboard_router
from app.api.routes.class_memberships import router as class_memberships_router
from app.api.routes.health import router as health_router
from app.api.routes.live import router as live_router
from app.api.routes.me import router as me_router
from app.api.routes.quizzes import router as quizzes_router
from app.api.routes.responses import router as responses_router
from app.api.routes.sessions import router as sessions_router

api_router = APIRouter()
api_router.include_router(class_dashboard_router)
api_router.include_router(class_memberships_router)
api_router.include_router(health_router)
api_router.include_router(live_router)
api_router.include_router(me_router)
api_router.include_router(quizzes_router)
api_router.include_router(responses_router)
api_router.include_router(sessions_router)
