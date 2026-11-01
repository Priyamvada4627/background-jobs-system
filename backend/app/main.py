from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.router import api_router
from app.db.session import close_db_connection
from app.queue.connection import close_redis_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application startup logic
    yield
    # Application shutdown logic: gracefully close connections
    await close_db_connection()
    await close_redis_connection()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="A distributed, failure-resilient task queue and execution engine",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def redirect_duplicate_slashes(request, call_next):
    """Normalizes paths containing duplicate slashes (e.g. //stats -> /stats) via 307 redirect."""
    if "//" in request.url.path:
        import re
        from starlette.responses import RedirectResponse
        clean_path = re.sub(r"/+", "/", request.url.path)
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(url=f"{clean_path}{query}", status_code=307)
    return await call_next(request)

# Register main API router
app.include_router(api_router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running",
        "documentation": "/docs",
        "dashboard": "/dashboard",
    }
