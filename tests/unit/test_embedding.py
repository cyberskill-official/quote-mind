"""FR-041 embedding pipeline: frozen model + dimension, batches capped at 10, order preserved."""

from __future__ import annotations

from typing import Any

from quotemind.config.models import EMBED_DIMENSIONS, MODEL_EMBED
from quotemind.memory.embedding import MAX_BATCH, embed_text, embed_texts


class _Datum:
    def __init__(self, index: int, embedding: list[float]) -> None:
        self.index = index
        self.embedding = embedding


class _Response:
    def __init__(self, data: list[_Datum]) -> None:
        self.data = data


class _Embeddings:
    def __init__(self, recorder: list[dict[str, Any]]) -> None:
        self._recorder = recorder

    def create(self, *, model: str, input: list[str], dimensions: int) -> _Response:
        self._recorder.append({"model": model, "input": input, "dimensions": dimensions})
        # Return out of order on purpose: the pipeline must restore input order by index.
        data = [_Datum(i, [float(i)] * dimensions) for i in range(len(input))]
        return _Response(list(reversed(data)))


class _Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.embeddings = _Embeddings(self.calls)


class _Settings:
    dashscope_api_key = "sk-test"
    dashscope_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


def test_embed_texts_uses_frozen_model_and_dimension() -> None:
    client = _Client()
    vectors = embed_texts(["a", "b"], _Settings(), client=client)
    assert len(vectors) == 2
    assert all(len(vector) == EMBED_DIMENSIONS for vector in vectors)
    assert client.calls[0]["model"] == MODEL_EMBED
    assert client.calls[0]["dimensions"] == EMBED_DIMENSIONS


def test_embed_texts_batches_at_ten_and_preserves_order() -> None:
    client = _Client()
    texts = [f"t{i}" for i in range(23)]
    vectors = embed_texts(texts, _Settings(), client=client)

    assert len(vectors) == 23
    assert [len(call["input"]) for call in client.calls] == [MAX_BATCH, MAX_BATCH, 3]
    # Each batch's vectors come back in input order despite the reversed response.
    assert vectors[0][0] == 0.0 and vectors[9][0] == 9.0
    assert vectors[10][0] == 0.0  # second batch restarts its own index
    assert vectors[22][0] == 2.0


def test_embed_text_returns_a_single_vector_and_empty_is_noop() -> None:
    client = _Client()
    assert len(embed_text("one", _Settings(), client=client)) == EMBED_DIMENSIONS
    assert embed_texts([], _Settings(), client=client) == []
