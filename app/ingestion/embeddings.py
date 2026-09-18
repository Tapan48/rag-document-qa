import openai

from app.config import settings

_client = openai.OpenAI(api_key=settings.openai_api_key)

_TRANSIENT_OPENAI_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class EmbeddingError(Exception):
    """Permanent embedding failure (bad input, dimension mismatch, auth, etc.)."""


class EmbeddingTransientError(Exception):
    """Transient embedding failure worth retrying (timeouts, rate limits, connection errors)."""


def embed_texts(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    if not texts:
        return []

    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            response = _client.embeddings.create(model=settings.embedding_model, input=batch)
        except _TRANSIENT_OPENAI_ERRORS as exc:
            raise EmbeddingTransientError(str(exc)) from exc
        except openai.OpenAIError as exc:
            raise EmbeddingError(str(exc)) from exc

        for item in response.data:
            if len(item.embedding) != settings.embedding_dimensions:
                raise EmbeddingError(
                    f"Expected {settings.embedding_dimensions}-dim embedding, "
                    f"got {len(item.embedding)}"
                )
            vectors.append(item.embedding)
    return vectors
