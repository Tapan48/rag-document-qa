import uuid

from pydantic import BaseModel


class CitationOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    source_metadata: dict
    text: str
