import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings


def setup_logger() -> logging.Logger:
    """
    Set up a rotating file logger for API requests.

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger("api_requests")
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Prevent duplicate handlers if logger already exists
    if logger.handlers:
        return logger

    # Calculate max bytes from MB
    max_bytes = settings.LOG_MAX_SIZE_MB * 1024 * 1024

    # Create rotating file handler
    file_handler = RotatingFileHandler(
        filename=logs_dir / "api_requests.log",
        maxBytes=max_bytes,
        backupCount=settings.LOG_MAX_FILES,
        encoding="utf-8",
    )

    # Create formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S.%f"
    )
    formatter.formatTime = lambda record, datefmt: logging.Formatter.formatTime(
        formatter, record, datefmt
    )[:-3]  # Trim to milliseconds

    file_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(file_handler)

    return logger


# Create global logger instance
api_logger = setup_logger()
