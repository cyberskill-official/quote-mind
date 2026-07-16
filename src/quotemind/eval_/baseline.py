"""TASK-122: the single-agent baseline.

This is the honest control. One monolithic ReActAgent gets the same models, the same catalog, and
the same task - read the RFQ, pick the SKUs, price it - but with the architecture removed:

    no deterministic pricing engine   the model does the arithmetic itself
    no critic                          nothing recomputes the total
    no SKU whitelist                   the model may name any string it likes
    no validation gate                 nothing stops a quote with a missing quantity
    no separate parse/match stages     one prompt, one pass

Everything else is held constant on purpose. If the baseline used a weaker model, or fewer
candidates, or a worse prompt, then any gap we measured would be a gap we manufactured. The only
variable is the architecture, which is the thing the hackathon track is actually about.

The prediction that follows from the design: the baseline will be *fluent* and often get the items
roughly right, and it will get the money wrong - because LLMs cannot reliably do VND arithmetic with
8% VAT across multiple lines, and nothing here checks it.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from agentscope.message import Msg
from pydantic import BaseModel, Field

from ..agents.model import UsageSink, build_agent
from ..config.models import MODEL_PLANNER
from ..config.settings import Settings
from ..memory.embedding import embed_text
from ..memory.store import MemoryFacade
from ..models import CatalogProduct

TOP_K = 8  # the same retrieval budget the pipeline's matcher gets

BASELINE_SYS = """You are a sales quotation assistant for a Vietnamese IT reseller.

You will be given a customer's RFQ and a catalog of candidate products with their prices in VND.

Produce the complete quotation in one pass:
- read the RFQ and identify every line item the customer wants, with quantities
- choose the best matching product for each line from the catalog
- work out the unit price, the line total, the VAT, and the grand total in VND
- VAT is 8% for IT goods and services, and 10% for telecom services

Return the finished quotation. Be accurate with the numbers - the customer will be invoiced from
this document."""


class BaselineLine(BaseModel):
    description: str
    sku: str = Field(description="the SKU you chose from the catalog")
    qty: int
    unit_price_vnd: int = Field(description="unit price in VND")
    line_total_vnd: int = Field(description="qty * unit price, in VND")


class BaselineQuote(BaseModel):
    """What the single agent must produce on its own - including the money."""

    lines: list[BaselineLine] = Field(default_factory=list)
    subtotal_vnd: int = 0
    vat_vnd: int = 0
    total_vnd: int = Field(default=0, description="subtotal + VAT, in VND")


def _catalog_line(product: CatalogProduct) -> str:
    return (
        f"- SKU {product.sku} | {product.name.vi} / {product.name.en} | "
        f"đơn vị {product.unit} | giá niêm yết {product.list_price_vnd:,} VND | "
        f"giá đại lý {product.dealer_price_vnd:,} VND | VAT {product.vat_rate}%"
    )


async def baseline_quote(
    text: str,
    *,
    settings: Settings,
    facade: MemoryFacade,
    usage: UsageSink | None = None,
) -> BaselineQuote:
    """Run the monolithic agent over one RFQ and return whatever quote it produces.

    Retrieval is kept - a fair baseline still gets to see the catalog, it just gets it flattened
    into one prompt instead of a per-line matching stage. Denying it the catalog entirely would be
    a straw man.
    """
    query_vector = embed_text(text, settings, usage=usage)
    candidates: dict[str, CatalogProduct] = {}
    for product, _ in facade.search_catalog_vector(query_vector, top_k=TOP_K * 3):
        candidates.setdefault(product.sku, product)
    for product, _ in facade.search_catalog_text(text, limit=TOP_K * 3):
        candidates.setdefault(product.sku, product)

    catalog_block = "\n".join(_catalog_line(product) for product in candidates.values())
    agent = build_agent(
        name="SingleAgent",
        sys_prompt=BASELINE_SYS,
        model_name=MODEL_PLANNER,
        settings=settings,
        usage=usage,
    )
    prompt = f"RFQ:\n{text}\n\nCatalog candidates:\n{catalog_block}"
    reply = await agent(Msg("user", prompt, "user"), structured_model=BaselineQuote)

    metadata = reply.metadata or {}
    try:
        return BaselineQuote.model_validate(metadata)
    except (ValueError, InvalidOperation):
        return BaselineQuote()  # a malformed answer is a failed case, not a crashed run


def baseline_total(quote: BaselineQuote) -> Decimal:
    return Decimal(quote.total_vnd)
