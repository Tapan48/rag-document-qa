from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://rag:rag@db:5432/rag"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    openai_api_key: str = ""
    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 20
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100


settings = Settings()
