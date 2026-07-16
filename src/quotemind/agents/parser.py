"""AGT-03 DocumentParser: text RFQ extraction (TASK-030).

The model returns a structured RFQExtraction (DM-03) directly - it never computes anything. The
deterministic TASK-034 gate in quotemind.parsing decides whether the result may proceed.
"""

from __future__ import annotations

from agentscope.message import Msg

from ..config.models import MODEL_PARSER_TEXT
from ..config.settings import Settings
from ..models import RFQExtraction
from ..prompts import PARSER_SYS
from .model import UsageSink, build_agent


async def extract_text_rfq(
    text: str, settings: Settings, *, usage: UsageSink | None = None
) -> RFQExtraction:
    """TASK-030: extract an RFQExtraction from Vietnamese or English RFQ text."""
    agent = build_agent(
        name="parser",
        sys_prompt=PARSER_SYS,
        model_name=MODEL_PARSER_TEXT,
        settings=settings,
        usage=usage,
    )
    reply = await agent(Msg("user", text, "user"), structured_model=RFQExtraction)
    return RFQExtraction.model_validate(reply.metadata)
