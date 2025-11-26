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

    # JWT Authentication configuration
    JWT_SECRET_KEY: str  # Required, generate with: openssl rand -hex 32
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 10080  # 7 days

    # Exchange Rate API configuration
    EXCHANGE_RATE_API_KEY: str  # Required, get from exchangerate-api.com
    EXCHANGE_RATE_API_TIMEOUT_SECONDS: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
