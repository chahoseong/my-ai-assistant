from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.security import normalize_username


class SignupRequest(BaseModel):
    username: str
    password: str = Field(min_length=15, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def canonicalize_username(cls, value: str) -> str:
        return normalize_username(value)


class LoginRequest(SignupRequest):
    pass


class PublicUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    created_at: datetime


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime


class ConversationMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=8_000)


class StreamUsagePayload(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    context_limit: int | None = Field(default=None, gt=0)


class StreamDonePayload(BaseModel):
    usage: StreamUsagePayload


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
