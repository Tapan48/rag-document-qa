import uuid

from pydantic import BaseModel, Field, field_validator


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[uuid.UUID] | None = None

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value

    @field_validator("document_ids")
    @classmethod
    def document_ids_not_explicit_empty(cls, value: list[uuid.UUID] | None):
        if value is not None and len(value) == 0:
            raise ValueError(
                "document_ids must not be an empty list; omit it to search all documents"
            )
        return value


class CitationOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    source_metadata: dict
    text: str


class QuestionResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    insufficient_evidence: bool
