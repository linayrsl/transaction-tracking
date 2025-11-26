from datetime import datetime
from pydantic import BaseModel, field_validator
import re


class UserRegister(BaseModel):
    email: str
    password: str

    @field_validator("email")
    def validate_email(cls, v):
        # Basic regex validation
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError("Invalid email format")
        return v.lower().strip()

    @field_validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain digit")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError("Password must contain special character")
        return v


class UserLogin(BaseModel):
    """Schema for JSON-based login endpoint."""

    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: str | None = None


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    created_at: datetime
