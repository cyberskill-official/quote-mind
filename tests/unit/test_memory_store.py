"""FR-040..043: the memory adapter translates DM models to and from the SDK records.

The SDK stores are mocked; these tests exercise the translation logic (Document build,
payload round-trip, hit mapping, session/message shaping), not live Tablestore.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tablestore_for_agent_memory.base.base_knowledge_store import Document, DocumentHit
from tablestore_for_agent_memory.base.common import Response

from quotemind.memory.store import TENANT_CATALOG, TENANT_CUSTOMERS, MemoryFacade, episodic_tenant
from quotemind.models import (
    BilingualText,
    CatalogProduct,
    Category,
    CustomerProfile,
    StockStatus,
    Tier,
)

_BT = BilingualText(vi="Máy tính xách tay", en="Laptop")


def _facade() -> MemoryFacade:
    return MemoryFacade(MagicMock(), MagicMock())


def _product() -> CatalogProduct:
    return CatalogProduct(
        sku="DELL-LAT-5450",
        brand="Dell",
        category=Category.LAPTOP,
        name=_BT,
        unit="chiếc",
        list_price_vnd=32_000_000,
        dealer_price_vnd=30_000_000,
        cost_price_vnd=28_000_000,
        vat_rate=8,
        stock_status=StockStatus.IN_STOCK,
        lead_time_days=7,
        warranty_months=36,
    )


def test_put_catalog_builds_document() -> None:
    facade = _facade()
    product = _product()
    facade.put_catalog(product, [0.1] * 1024)
    document = facade.knowledge.put_document.call_args.args[0]
    assert document.document_id == product.sku
    assert document.tenant_id == TENANT_CATALOG
    assert document.metadata["category"] == "laptop"
    assert document.metadata["list_price_vnd"] == 32_000_000
    assert CatalogProduct.model_validate_json(document.metadata["payload_json"]) == product


def test_get_catalog_parses_payload_or_none() -> None:
    facade = _facade()
    product = _product()
    facade.knowledge.get_document.return_value = Document(
        document_id=product.sku,
        tenant_id=TENANT_CATALOG,
        metadata={"payload_json": product.model_dump_json()},
    )
    assert facade.get_catalog(product.sku) == product
    facade.knowledge.get_document.return_value = None
    assert facade.get_catalog("missing") is None


def test_search_catalog_vector_maps_hits() -> None:
    facade = _facade()
    product = _product()
    document = Document(
        document_id=product.sku,
        tenant_id=TENANT_CATALOG,
        metadata={"payload_json": product.model_dump_json()},
    )
    facade.knowledge.vector_search.return_value = Response(
        hits=[DocumentHit(document=document, score=0.87)]
    )
    results = facade.search_catalog_vector([0.0] * 1024, top_k=3)
    assert results == [(product, 0.87)]


def test_put_customer_and_tenant() -> None:
    facade = _facade()
    profile = CustomerProfile(customer_id="cust_thanhcong", name="Thành Công", tier=Tier.DEALER)
    facade.put_customer(profile)
    document = facade.knowledge.put_document.call_args.args[0]
    assert document.tenant_id == TENANT_CUSTOMERS
    assert document.metadata["tier"] == "dealer"
    assert CustomerProfile.model_validate_json(document.metadata["payload_json"]) == profile


def test_episodic_tenant_is_frozen_shape() -> None:
    assert episodic_tenant("cust_thanhcong") == "episodic:cust_thanhcong"


def test_sessions_and_messages_delegate() -> None:
    facade = _facade()
    facade.put_session("user-1", "sess-1", {"channel": "paste"})
    session = facade.memory.put_session.call_args.args[0]
    assert session.user_id == "user-1"
    assert session.session_id == "sess-1"

    facade.add_message("sess-1", "msg-1", "xin chào")
    message = facade.memory.put_message.call_args.args[0]
    assert message.session_id == "sess-1"
    assert message.content == "xin chào"


def test_init_tables_calls_sdk() -> None:
    facade = _facade()
    facade.init_tables()
    facade.memory.init_table.assert_called_once()
    facade.memory.init_search_index.assert_called_once()
    facade.knowledge.init_table.assert_called_once()
