from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://rag:rag@db:5432/rag"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    registration_enabled: bool = True
    # Explicit mode takes precedence over the legacy development toggle.
    registration_mode: Literal["open", "approval", "closed"] | None = None
    public_app_url: str = "http://localhost:5173"
    access_notification_email: str = "tapangarasangi@gmail.com"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")

    @property
    def effective_registration_mode(self) -> str:
        return self.registration_mode or ("open" if self.registration_enabled else "closed")

    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    openai_api_key: str = ""
    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 20
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100

    chat_model: str = "gpt-5.6-luna"
    reasoning_effort: str = "none"
    retrieval_top_k: int = 5
    max_output_tokens: int = 1000
    web_search_model: str = "gpt-5.6-luna"
    web_search_max_tool_calls: int = Field(default=3, ge=1, le=10)
    web_search_timeout_seconds: float = Field(default=90.0, gt=0, le=300)
    answer_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    web_search_max_output_tokens: int = Field(default=3000, ge=500, le=10000)


settings = Settings()
