"""Adapter over tablestore-for-agent-memory (FR-040..043).

This is the thin isolation layer for the riskiest external contract (Risk #2). The SDK
layout was verified against the installed 1.1.3 wheel (Appendix E.1) and differs from the
spec's assumed paths: MemoryStore lives in tablestore_for_agent_memory.memory.memory_store,
KnowledgeStore in tablestore_for_agent_memory.knowledge.knowledge_store, and filters in
base.filter. Document/Session/Message metadata holds only scalar values, so each aggregate is
stored as a `payload_json` string plus filterable scalar fields, and reconstructed on read.

Constructing the facade is offline; init_tables() and every read/write require a live
Tablestore instance and are exercised by provisioning and integration, not unit tests.
"""

from __future__ import annotations

import hashlib
from typing import Any, TypeVar

from pydantic import BaseModel
from tablestore_for_agent_memory.base.base_knowledge_store import Document
from tablestore_for_agent_memory.base.base_memory_store import Message, Session
from tablestore_for_agent_memory.knowledge.knowledge_store import KnowledgeStore
from tablestore_for_agent_memory.memory.memory_store import MemoryStore

from ..config.models import EMBED_DIMENSIONS
from ..config.settings import Settings
from ..models import CatalogProduct, CustomerProfile, EpisodicQuoteMemory, SOPSnippet

# Frozen KnowledgeStore tenants (parent 12.5).
TENANT_CATALOG = "catalog"
TENANT_CUSTOMERS = "customers"
TENANT_SOP = "sop"
_PAYLOAD = "payload_json"

_M = TypeVar("_M", bound=BaseModel)


def episodic_tenant(customer_id: str) -> str:
    """Frozen per-customer episodic tenant name (parent 12.5)."""
    return f"episodic:{customer_id}"


def _catalog_text(product: CatalogProduct) -> str:
    specs = " ".join(f"{key}={value}" for key, value in sorted(product.specs.items()))
    return f"{product.name.vi} {product.name.en} {specs}".strip()


def _parse(document: Document | None, model: type[_M]) -> _M | None:
    if document is None or document.metadata is None:
        return None
    payload = document.metadata.get(_PAYLOAD)
    if not isinstance(payload, str):
        return None
    return model.model_validate_json(payload)


def _hits(response: Any, model: type[_M]) -> list[tuple[_M, float]]:
    results: list[tuple[_M, float]] = []
    for hit in response.hits or []:
        parsed = _parse(hit.document, model)
        if parsed is not None:
            results.append((parsed, hit.score or 0.0))
    return results


class MemoryFacade:
    """DM-model-facing wrapper over the SDK's MemoryStore and KnowledgeStore."""

    def __init__(self, memory_store: MemoryStore, knowledge_store: KnowledgeStore) -> None:
        self.memory = memory_store
        self.knowledge = knowledge_store

    @classmethod
    def from_settings(cls, settings: Settings) -> MemoryFacade:
        """Build the SDK stores from configuration. Requires live Tablestore access."""
        from tablestore import OTSClient

        client = OTSClient(
            settings.tablestore_endpoint,
            settings.alibaba_cloud_access_key_id,
            settings.alibaba_cloud_access_key_secret,
            settings.tablestore_instance,
        )
        memory_store = MemoryStore(tablestore_client=client)
        knowledge_store = KnowledgeStore(
            tablestore_client=client,
            vector_dimension=EMBED_DIMENSIONS,
            enable_multi_tenant=True,
        )
        return cls(memory_store, knowledge_store)

    def init_tables(self) -> None:
        """Idempotently create the backing tables and indexes (used by provisioning)."""
        self.memory.init_table()
        self.memory.init_search_index()
        self.knowledge.init_table()

    # --- catalog: hybrid semantic + full-text retrieval ---
    def put_catalog(self, product: CatalogProduct, embedding: list[float]) -> None:
        self.knowledge.put_document(
            Document(
                document_id=product.sku,
                tenant_id=TENANT_CATALOG,
                text=_catalog_text(product),
                embedding=embedding,
                metadata={
                    _PAYLOAD: product.model_dump_json(),
                    "sku": product.sku,
                    "brand": product.brand,
                    "category": product.category.value,
                    "list_price_vnd": product.list_price_vnd,
                    "vat_rate": product.vat_rate,
                    "stock_status": product.stock_status.value,
                },
            )
        )

    def get_catalog(self, sku: str) -> CatalogProduct | None:
        return _parse(self.knowledge.get_document(sku, tenant_id=TENANT_CATALOG), CatalogProduct)

    def search_catalog_vector(
        self, query_vector: list[float], top_k: int = 10
    ) -> list[tuple[CatalogProduct, float]]:
        response = self.knowledge.vector_search(
            query_vector=query_vector,
            top_k=top_k,
            tenant_id=TENANT_CATALOG,
            meta_data_to_get=[_PAYLOAD],
        )
        return _hits(response, CatalogProduct)

    def search_catalog_text(
        self, query: str, limit: int = 10
    ) -> list[tuple[CatalogProduct, float]]:
        response = self.knowledge.full_text_search(
            query=query, tenant_id=TENANT_CATALOG, limit=limit, meta_data_to_get=[_PAYLOAD]
        )
        return _hits(response, CatalogProduct)

    # --- customers ---
    def put_customer(self, profile: CustomerProfile) -> None:
        self.knowledge.put_document(
            Document(
                document_id=profile.customer_id,
                tenant_id=TENANT_CUSTOMERS,
                text=profile.name,
                metadata={_PAYLOAD: profile.model_dump_json(), "tier": profile.tier.value},
            )
        )

    def get_customer(self, customer_id: str) -> CustomerProfile | None:
        document = self.knowledge.get_document(customer_id, tenant_id=TENANT_CUSTOMERS)
        return _parse(document, CustomerProfile)

    # --- episodic memory (per customer) ---
    def put_episodic(
        self, memory: EpisodicQuoteMemory, customer_id: str, embedding: list[float]
    ) -> None:
        self.knowledge.put_document(
            Document(
                document_id=memory.memory_id,
                tenant_id=episodic_tenant(customer_id),
                text=f"{memory.summary.vi} {memory.summary.en}",
                embedding=embedding,
                metadata={
                    _PAYLOAD: memory.model_dump_json(),
                    "importance": memory.importance,
                    "quote_number": memory.quote_number,
                },
            )
        )

    def search_episodic(
        self, customer_id: str, query_vector: list[float], top_k: int = 5
    ) -> list[tuple[EpisodicQuoteMemory, float]]:
        response = self.knowledge.vector_search(
            query_vector=query_vector,
            top_k=top_k,
            tenant_id=episodic_tenant(customer_id),
            meta_data_to_get=[_PAYLOAD],
        )
        return _hits(response, EpisodicQuoteMemory)

    # --- SOP snippets ---
    def put_sop(self, snippet: SOPSnippet, embedding: list[float]) -> None:
        digest = hashlib.sha1(snippet.text.vi.encode("utf-8")).hexdigest()[:8]
        self.knowledge.put_document(
            Document(
                document_id=f"sop:{snippet.topic.value}:{digest}",
                tenant_id=TENANT_SOP,
                text=f"{snippet.text.vi} {snippet.text.en}",
                embedding=embedding,
                metadata={_PAYLOAD: snippet.model_dump_json(), "topic": snippet.topic.value},
            )
        )

    def search_sop(
        self, query_vector: list[float], top_k: int = 5
    ) -> list[tuple[SOPSnippet, float]]:
        response = self.knowledge.vector_search(
            query_vector=query_vector,
            top_k=top_k,
            tenant_id=TENANT_SOP,
            meta_data_to_get=[_PAYLOAD],
        )
        return _hits(response, SOPSnippet)

    # --- sessions and messages (working memory) ---
    def put_session(
        self, user_id: str, session_id: str, metadata: dict[str, Any] | None = None
    ) -> None:
        self.memory.put_session(
            Session(user_id=user_id, session_id=session_id, metadata=metadata or {})
        )

    def get_session(self, user_id: str, session_id: str) -> Session | None:
        return self.memory.get_session(user_id, session_id)

    def add_message(
        self, session_id: str, message_id: str, content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        self.memory.put_message(
            Message(
                session_id=session_id,
                message_id=message_id,
                content=content,
                metadata=metadata or {},
            )
        )

    def list_messages(self, session_id: str) -> list[Message]:
        return list(self.memory.list_messages(session_id))
