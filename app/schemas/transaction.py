import re
from datetime import datetime

from pydantic import BaseModel, field_validator, field_serializer

from app.core.constants import SUPPORTED_CURRENCIES


class TransactionCreate(BaseModel):
    """Schema for creating a transaction."""

    amount: float
    currency: str

    @field_validator("amount")
    def validate_amount(cls, v):
        """Validate amount has max 2 decimal places."""
        if v <= 0:
            raise ValueError("Amount must be positive")
        # Round to 2 decimal places to handle floating point precision
        rounded = round(v, 2)
        return rounded

    @field_validator("currency")
    def validate_currency(cls, v):
        """Validate currency is supported 3-letter code."""
        v = v.upper()  # Enforce uppercase

        # Validate format
        if not re.match(r"^[A-Z]{3}$", v):
            raise ValueError("Currency must be a 3-letter code")

        # Validate against whitelist
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError("Currency code not supported")

        return v


class TransactionResponse(BaseModel):
    """Schema for transaction response."""

    model_config = {"from_attributes": True}

    id: int
    amount: float  # Return as float (will convert from cents)
    currency: str
    created_at: datetime

    @field_serializer("amount")
    def serialize_amount(self, amount: int) -> float:
        """Convert amount from micro cents (integer) to float."""
        return amount / 10000.0


class TransactionListResponse(BaseModel):
    """Paginated list of transactions."""

    items: list[TransactionResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class CurrencySummary(BaseModel):
    """Summary of transactions for a single currency."""

    currency: str
    total: float
