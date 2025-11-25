from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    PROJECT_NAME: str = "Transaction Tracking API"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Logging configuration
    LOG_MAX_FILES: int = 5
    LOG_MAX_SIZE_MB: int = 5
    LOG_EXCLUDED_PATHS: list[str] = [
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    ]
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
