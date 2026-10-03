from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_MIN = 12
PASSWORD_MAX = 128


def _normalize_email(v: str) -> str:
    return v.strip().lower()


class RegisterRequest(BaseModel):
    email: EmailStr = Field(examples=["demo@example.com"])
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)

    _norm = field_validator("email", mode="after")(_normalize_email)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX)

    _norm = field_validator("email", mode="after")(_normalize_email)


class UserOut(BaseModel):
    """Safe profile: never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")
