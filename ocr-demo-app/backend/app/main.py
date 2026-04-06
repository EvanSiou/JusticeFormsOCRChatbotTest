"""OCR Demo App — FastAPI entry point."""
import os
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import processing, setup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="OCR Demo App", version="1.0.0")

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(processing.router, prefix="/api/processing", tags=["processing"])
app.include_router(setup.router, prefix="/api/setup", tags=["setup"])


@app.on_event("startup")
async def startup():
    try:
        from .services.seed_data import seed_defaults
        seed_defaults()
    except Exception as e:
        logger.warning(f"Seed data failed (non-fatal): {e}")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files (production — built frontend copied to ./static)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    from fastapi.responses import FileResponse

    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    # SPA catch-all: serve index.html for any non-API route (handles page refresh)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # If it's a file that exists, serve it
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Otherwise serve index.html (SPA routing)
        return FileResponse(str(static_dir / "index.html"))

    logger.info(f"Serving frontend from {static_dir}")
