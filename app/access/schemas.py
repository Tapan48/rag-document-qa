import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AccessRequestCreate(BaseModel):
    email: EmailStr


class InvitationCheck(BaseModel):
    token: str = Field(min_length=64, max_length=64)


class EmailPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    status: str
    attempts: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class AccessRequestPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    status: str
    expires_at: datetime | None
    created_at: datetime
    deliveries: list[EmailPublic] = []
