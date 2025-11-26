from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import auth
from app.config import settings
from app.core.middleware import RequestLoggingMiddleware, UserInjectionMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add user injection middleware (runs second - parses JWT and injects user)
app.add_middleware(UserInjectionMiddleware)

# Add request logging middleware (runs third - uses injected user for logging)
app.add_middleware(RequestLoggingMiddleware)

# Include auth router at root level (no prefix)
app.include_router(auth.router, tags=["auth"])


@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
