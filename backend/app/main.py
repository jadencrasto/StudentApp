"""
SAIS Backend — main.py
Entry point. Run with: uvicorn app.main:app --reload
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.core.rate_limiter import limiter
from app.database import (
    engine, Base,
    ensure_assignment_ai_metadata_column, ensure_assignment_classroom_id_column,
    ensure_activity_recurrence_columns, ensure_notification_columns,
    ensure_attendance_slot_columns, ensure_phase5a_columns, ensure_phase6a_columns,
    ensure_phase6b_tables, ensure_phase6c_tables, ensure_phase6d_tables,
)
from app.models import *  # noqa

from app.api.auth        import router as auth_router
from app.api.assignments import router as assignments_router
from app.api.attendance  import router as attendance_router
from app.api.activities  import router as activities_router
from app.api.documents   import router as documents_router
from app.api.alerts      import router as alerts_router
from app.api.timetable   import router as timetable_router
from app.api.extract     import router as extract_router
from app.api.college_events import router as college_events_router
from app.api.classroom import router as classroom_router, oauth_router as google_oauth_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.institutions import router as institutions_router
from app.api.join import router as join_router
from app.api.admin_students import router as admin_students_router
from app.api.class_attendance import router as class_attendance_router
from app.api.class_timetable import router as class_timetable_router
from app.api.class_marks import router as class_marks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    if settings.DATABASE_URL.startswith("sqlite"):
        if settings.DEBUG:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        await ensure_assignment_ai_metadata_column()
        await ensure_assignment_classroom_id_column()
        await ensure_activity_recurrence_columns()
        await ensure_notification_columns()
        await ensure_attendance_slot_columns()
        await ensure_phase5a_columns()
        await ensure_phase6a_columns()
        await ensure_phase6b_tables()
        await ensure_phase6c_tables()
        await ensure_phase6d_tables()
    # Seed demo user for development only if explicitly enabled
    if settings.SEED_DEMO_USER:
        await _seed_demo_user()
    from app.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    try:
        yield
    except asyncio.CancelledError:
        # Suppress starlette/uvicorn shutdown race — not an application error
        pass
    finally:
        stop_scheduler()
        await engine.dispose()


async def _seed_demo_user():
    """Create demo user on startup if it doesn't exist."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models.user import User
    from app.core.security import hash_password

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "demo@sais.edu"))
        if result.scalar_one_or_none() is None:
            user = User(
                email="demo@sais.edu",
                username="demo",
                full_name="Demo Student",
                hashed_password=hash_password("password123"),
            )
            db.add(user)
            await db.commit()
            print("[SAIS] Seeded demo user: demo@sais.edu / password123")


app = FastAPI(
    title="SAIS — Smart Academic Intelligence System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
    redirect_slashes=False,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Please slow down and try again later."},
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# Versioned API Router
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(assignments_router)
api_router.include_router(attendance_router)
api_router.include_router(activities_router)
api_router.include_router(documents_router)
api_router.include_router(alerts_router)
api_router.include_router(timetable_router)
api_router.include_router(college_events_router)
api_router.include_router(classroom_router)
api_router.include_router(chat_router)
api_router.include_router(dashboard_router)
api_router.include_router(institutions_router)
api_router.include_router(join_router)
api_router.include_router(admin_students_router)
api_router.include_router(class_attendance_router)
api_router.include_router(class_timetable_router)
api_router.include_router(class_marks_router)

app.include_router(api_router)
app.include_router(extract_router)
app.include_router(google_oauth_router)  # OAuth at root: /auth/google/*


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
