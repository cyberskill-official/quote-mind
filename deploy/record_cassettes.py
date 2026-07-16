"""TASK-123: record the CI cassettes from a live run.

    python deploy/record_cassettes.py

Runs 5 designated cases against the real models and freezes what they said. The recording is taken
from the pipeline's own reasoning trace (TASK-111, TRACE_CONTENT=1) rather than from a bespoke capture
path - so what CI replays is exactly what the models actually returned, not a parallel fiction that
could drift away from the real thing.
"""

from __future__ import annotations

import asyncio

from quotemind.agents.matcher import MatchSelection
from quotemind.config.seller import SELLER_BLOCK
from quotemind.config.settings import require_settings
from quotemind.eval_.cassette import Cassette, LineCassette
from quotemind.eval_.run import load_cases
from quotemind.memory.store import MemoryFacade
from quotemind.models import RFQExtraction
from quotemind.obs.trace import Tracer
from quotemind.orchestrator import quote_from_text

# Chosen to cover the paths CI must not regress on: a simple 2-line quote, a 3-line quote, the
# 10% telecom VAT rule, an out-of-catalog line, and a spec conflict.
CI_CASES = ["vi_text_001", "vi_text_003", "vi_text_010", "adv_001", "adv_002"]


def _harvest(case_id: str, tracer: Tracer) -> Cassette:
    """Pull the model turns back out of the trace."""
    document = tracer.document()
    by_seq = {content.seq: content for content in document.contents}
    extraction: RFQExtraction | None = None
    lines: list[LineCassette] = []
    pending: dict[str, list[str]] = {"vector": [], "text": []}

    for step in document.steps:
        content = by_seq.get(step.seq)
        if step.action == "parse" and content and content.response:
            extraction = RFQExtraction.model_validate_json(content.response)
        elif step.tool == "vector_search":
            pending["vector"] = list(step.memory_ids)
        elif step.tool == "full_text_search":
            pending["text"] = list(step.memory_ids)
        elif step.action == "select" and content and content.response:
            lines.append(
                LineCassette(
                    vector_skus=pending["vector"],
                    text_skus=pending["text"],
                    selection=MatchSelection.model_validate_json(content.response),
                )
            )
            pending = {"vector": [], "text": []}

    if extraction is None:
        raise RuntimeError(f"{case_id}: no parse step captured - is TRACE_CONTENT on?")
    return Cassette(case_id=case_id, extraction=extraction, lines=lines)


async def main_async() -> None:
    settings = require_settings()
    if not settings.trace_content:
        raise SystemExit("set TRACE_CONTENT=1 - the cassettes are harvested from the trace bodies")
    facade = MemoryFacade.from_settings(settings)
    cases = {case.case_id: case for case in load_cases()}

    for index, case_id in enumerate(CI_CASES, start=1):
        case = cases[case_id]
        tracer = Tracer(quote_id=case_id, include_content=True)
        await quote_from_text(
            case.input.text or "",
            settings=settings,
            facade=facade,
            seller_block=SELLER_BLOCK,
            sequence=index,
            customer_hint=case.labels.customer_id,
            tracer=tracer,
        )
        path = _harvest(case_id, tracer).save()
        print(f"recorded {case_id} -> {path}")


if __name__ == "__main__":  # pragma: no cover - operational script
    asyncio.run(main_async())
