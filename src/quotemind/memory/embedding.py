"""Embedding pipeline (FR-041).

Every KnowledgeStore document and every query vector is produced here, with the frozen model
(text-embedding-v4) at the frozen dimension (1024) and batches capped at 10 texts per call.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from ..config.models import EMBED_DIMENSIONS, MODEL_EMBED
from ..config.settings import Settings

MAX_BATCH = 10  # FR-041: embedding calls batched <= 10 texts


def build_embedding_client(settings: Settings) -> OpenAI:
    """OpenAI-compatible DashScope client (the embeddings endpoint speaks that dialect)."""
    return OpenAI(api_key=settings.dashscope_api_key, base_url=settings.dashscope_base_url)


def embed_texts(
    texts: list[str], settings: Settings, *, client: Any | None = None
) -> list[list[float]]:
    """Embed texts in input order, batching at MAX_BATCH, always at EMBED_DIMENSIONS."""
    if not texts:
        return []
    embedder = client if client is not None else build_embedding_client(settings)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), MAX_BATCH):
        chunk = texts[start : start + MAX_BATCH]
        response = embedder.embeddings.create(
            model=MODEL_EMBED, input=chunk, dimensions=EMBED_DIMENSIONS
        )
        for item in sorted(response.data, key=lambda datum: datum.index):
            vectors.append(list(item.embedding))
    return vectors


def embed_text(text: str, settings: Settings, *, client: Any | None = None) -> list[float]:
    """Embed a single text (query vector)."""
    return embed_texts([text], settings, client=client)[0]
