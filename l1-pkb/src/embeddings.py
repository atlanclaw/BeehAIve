"""Embedding service abstraction using sentence-transformers."""

import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from .config import config

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Get or initialize the embedding model (singleton)."""
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", config.EMBEDDING_MODEL)
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
        logger.info("Embedding model loaded. Dimension: %d", _model.get_sentence_embedding_dimension())
    return _model


def embed_text(text: str) -> list[float]:
    """Generate embedding vector for a single text."""
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Generate embedding vectors for a batch of texts."""
    model = get_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return embeddings.tolist()


@lru_cache(maxsize=1)
def get_embedding_dimension() -> int:
    """Return the embedding dimension for the current model."""
    model = get_model()
    return model.get_sentence_embedding_dimension()
