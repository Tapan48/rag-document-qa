import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus


class DocumentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: DocumentStatus
    error_message: str | None
    created_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentPublic]
    total: int
    limit: int
    offset: int
