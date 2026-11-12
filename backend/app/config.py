import os

from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


KNOWN_PLACEHOLDER_KEYS: set[str] = {
    "your-super-secret-key-change-this-in-production-min-32-chars",
    "change-me-in-production-super-secret-key-32chars",
    "your-secret-key-change-this-in-production",
}


class Settings(BaseSettings):
    # App
    APP_NAME: str = "SAIS"
    DEBUG: bool = False
    SEED_DEMO_USER: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"

    # Rate Limiting
    RATE_LIMIT_AUTH_PER_MINUTE: int = 20
    RATE_LIMIT_FAILED_LOGINS_PER_MINUTE: int = 5
    RATE_LIMIT_GENERAL_PER_MINUTE: int = 300

    # Database
    DATABASE_URL: str

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    # OCR
    TESSERACT_CMD: str = "tesseract"

    # AI Provider & Models
    AI_PROVIDER: str = "gemini"  # "gemini" or "ollama"
    AI_RATE_LIMIT_PER_HOUR: int = 30

    # Gemini AI
    GEMINI_API_KEY: str | None = None
    GEMINI_API_KEY_CHAT: str | None = None
    GEMINI_API_KEY_TIMETABLE: str | None = None
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    # Google Custom Search API (fallback for JS-heavy college sites)
    # Get a free key + CX at https://programmablesearch.google.com (100 queries/day free)
    GOOGLE_SEARCH_API_KEY: str = ""
    GOOGLE_SEARCH_CX: str = ""  # Custom Search Engine ID

    # Ollama (local AI)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # Google OAuth / Classroom
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = "http://127.0.0.1:8000/auth/google/callback"
    TOKEN_ENCRYPTION_KEY: str | None = None

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Environment & Security
    ENVIRONMENT: str = "development"  # "development", "production", "test"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    CSP_REPORT_ONLY: bool = True
    TRUSTED_PROXIES: str = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        val = (v or "").strip()
        if not val:
            raise ValueError("SECRET_KEY must not be empty")
        if len(val) < 32:
            raise ValueError(f"SECRET_KEY must be at least 32 characters long (got {len(val)})")
        if val in KNOWN_PLACEHOLDER_KEYS:
            raise ValueError(f"SECRET_KEY cannot use placeholder or default value: {val}")
        return val

    def validate_production_security(self) -> None:
        """Validate strict security gates for production mode at startup."""
        if (self.ENVIRONMENT or "").strip().lower() == "production":
            if self.DEBUG:
                raise RuntimeError("Production safety violation: DEBUG is True. Must be False in production.")
            if not self.COOKIE_SECURE:
                raise RuntimeError("Production safety violation: COOKIE_SECURE is False. Must be True in production.")
            if len(self.SECRET_KEY) < 32 or self.SECRET_KEY in KNOWN_PLACEHOLDER_KEYS:
                raise RuntimeError("Production safety violation: SECRET_KEY is default or weak (<32 characters).")

    # File uploads & Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    STORAGE_BACKEND: str = "supabase"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "sais-private"
    STORAGE_CLEANUP_DRY_RUN: bool = True

    def get_gemini_chat_key(self) -> str:
        key = self.GEMINI_API_KEY_CHAT or self.GEMINI_API_KEY
        if not key:
            raise RuntimeError(
                "Gemini API key for chat/estimation is not configured. "
                "Please set GEMINI_API_KEY_CHAT or GEMINI_API_KEY in your environment."
            )
        return key

    def get_gemini_timetable_key(self) -> str:
        key = self.GEMINI_API_KEY_TIMETABLE or self.GEMINI_API_KEY
        if not key:
            raise RuntimeError(
                "Gemini API key for timetable/events is not configured. "
                "Please set GEMINI_API_KEY_TIMETABLE or GEMINI_API_KEY in your environment."
            )
        return key

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
