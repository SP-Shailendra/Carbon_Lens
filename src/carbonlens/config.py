import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    database_path: str = field(
        default_factory=lambda: os.getenv("DATABASE_PATH", ".local/carbonlens.db")
    )
    api_key: str = field(default_factory=lambda: os.getenv("CARBONLENS_API_KEY", ""))
    api_url: str = field(
        default_factory=lambda: os.getenv("CARBONLENS_API_URL", "http://127.0.0.1:8001")
    )
    public_api_url: str = field(
        default_factory=lambda: os.getenv(
            "CARBONLENS_PUBLIC_API_URL", os.getenv("CARBONLENS_API_URL", "http://127.0.0.1:8001")
        )
    )
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "10")))
    factors_path: str = field(default_factory=lambda: os.getenv("EMISSION_FACTORS_PATH", ""))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))

    def __post_init__(self):
        if not 1 <= self.max_upload_mb <= 100:
            raise ValueError("MAX_UPLOAD_MB must be between 1 and 100.")
        if self.app_env == "production" and not self.api_key:
            raise ValueError("CARBONLENS_API_KEY is required in production.")


settings = Settings()
