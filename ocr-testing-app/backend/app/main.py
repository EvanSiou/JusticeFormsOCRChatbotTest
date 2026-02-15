"""
Court Form OCR Testing App - FastAPI Backend

Main application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.auth.routes import router as auth_router
from app.routers.forms import router as forms_router
from app.routers.synthetic import router as synthetic_router
from app.routers.tests import router as tests_router
from app.routers.results import router as results_router
from app.routers.metrics import router as metrics_router
from app.routers.verification import router as verification_router
from app.routers.cleaning import router as cleaning_router
from app.routers.classification import router as classification_router
from app.routers.classification_verification import router as classify_verify_router
from app.routers.prompts import router as prompts_router

settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Multi-user web application for testing OCR/layout detection pipelines on court forms.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(forms_router, prefix="/api/forms", tags=["Forms"])
app.include_router(synthetic_router, prefix="/api/synthetic", tags=["Synthetic Data"])
app.include_router(tests_router, prefix="/api/tests", tags=["Tests"])
app.include_router(results_router, prefix="/api/results", tags=["Results"])
app.include_router(metrics_router, prefix="/api/metrics", tags=["Metrics"])
app.include_router(verification_router, prefix="/api/verify", tags=["Verification"])
app.include_router(cleaning_router, prefix="/api/clean", tags=["Cleaning"])
app.include_router(classification_router, prefix="/api/classify", tags=["Classification"])
app.include_router(classify_verify_router, prefix="/api/classify-verify", tags=["Classification Verification"])
app.include_router(prompts_router, prefix="/api/prompts", tags=["Prompts"])


@app.get("/")
@app.get("/api/health")
async def health_check():
    """Health check endpoint (also serves root for Cloud Run health probes)."""
    return {"status": "healthy", "app": settings.app_name}


@app.get("/api/info")
async def app_info():
    """Get application info including available processors."""
    from app.processing.layout import list_layout_detectors
    from app.processing.ocr import list_ocr_engines

    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "available_layout_detectors": list_layout_detectors(),
        "available_ocr_engines": list_ocr_engines(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
