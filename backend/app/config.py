import os

from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


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

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("SECRET_KEY must not be empty")
        v = v.strip()
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        disallowed_terms = ["change-me", "placeholder", "your-super-secret", "default-secret", "secretkey"]
        v_lower = v.lower()
        if any(term in v_lower for term in disallowed_terms):
            raise ValueError("SECRET_KEY cannot be a default or placeholder value")
        return v

    # File uploads
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

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
