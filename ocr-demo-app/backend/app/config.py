"""Application configuration via environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AWS
    aws_default_region: str = "us-west-2"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_bearer_token_bedrock: str = ""

    # S3
    s3_bucket: str = "ocr-demo-documents"

    # DynamoDB table prefix
    dynamodb_table_prefix: str = "ocr-demo"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Assistant / RAG
    chroma_dir: str = "./app_data/chroma"
    legal_docs_dir: str = "./app/legal_docs"
    chat_model_name: str = "claude_bedrock"
    legal_top_k: int = 4
    session_top_k: int = 6
    text_chunk_size: int = 1200
    text_chunk_overlap: int = 150

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Table names
    @property
    def sessions_table(self) -> str:
        return f"{self.dynamodb_table_prefix}-sessions"

    @property
    def config_table(self) -> str:
        return f"{self.dynamodb_table_prefix}-config"

    @property
    def prompts_table(self) -> str:
        return f"{self.dynamodb_table_prefix}-prompts"

    @property
    def form_types_table(self) -> str:
        return f"{self.dynamodb_table_prefix}-form-types"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
