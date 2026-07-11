"""Model-calling agents (AGT-03 parser, AGT-04 catalog selector).

Everything deterministic - fusion, banding, pricing, assembly, the critic recompute - lives below
this layer. These modules are the only place a model is called on the quote path.
"""

from __future__ import annotations

from .matcher import MatchSelection, select_sku
from .model import build_agent, build_chat_model, native_base_url
from .parser import extract_text_rfq

__all__ = [
    "MatchSelection",
    "build_agent",
    "build_chat_model",
    "extract_text_rfq",
    "native_base_url",
    "select_sku",
]
