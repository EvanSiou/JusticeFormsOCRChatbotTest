"""
Application configuration using Pydantic settings.
Loads from environment variables or .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App settings
    app_name: str = "Court Form OCR Testing App"
    debug: bool = False

    # GCP Settings
    gcp_project_id: str = ""
    gcp_storage_bucket: str = ""
    google_application_credentials: str = ""

    # Auth settings
    secret_key: str = "change-this-in-production-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Claude API
    anthropic_api_key: str = ""

    # OpenAI API
    openai_api_key: str = ""

    # AWS Bedrock
    aws_bearer_token_bedrock: str = ""
    aws_default_region: str = "us-west-2"

    # CORS settings - stored as a plain string, parsed by get_cors_origins()
    cors_origins: str = "http://localhost:3000,http://localhost:5173,https://ocr-app-frontend-206256614025.us-central1.run.app"

    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
