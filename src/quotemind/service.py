"""Quote lifecycle service: intake, the persisted pipeline, and the human approval gate.

Every status change goes through the frozen state machine (FR-080) and is written to Tablestore with
a hash-chained audit event (FR-094) before the call returns. That is what makes FR-081 real: the
pipeline stops at `pending_approval` and nothing waits in memory, so an approval minutes later is
served by a different process that simply loads the record.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Any

from .cloud import ArtifactStore, artifact_key
from .config.settings import Settings
from .dispatch import send_quote
from .intake import classify, payload_hash
from .memory.quotes import QuoteStore, totals_of
from .memory.recall import write_episode
from .memory.store import MemoryFacade
from .models import (
    Actor,
    Channel,
    CriticReport,
    DocType,
    EmailMeta,
    Outcome,
    Quote,
    QuoteRecord,
    RFQExtraction,
    Status,
    assert_transition,
    new_ulid,
)
from .obs.log import log_event
from .obs.trace import Tracer
from .orchestrator import (
    PipelineResult,
    quote_from_excel,
    quote_from_image,
    quote_from_pdf,
    quote_from_revision,
    quote_from_text,
)
from .pricing import vat_policy_note
from .quote import format_quote_number, parse_quote_number
from .quote.render import render_pdf

MAX_REVISIONS = 3  # FR-064: after this many revisions the quote goes to a human
PENDING_REMINDER_HOURS = 4  # FR-085

SYSTEM = Actor(kind="system")
HUMAN = Actor(kind="human")
PIPELINE = Actor(kind="agent", name="orchestrator")

Pipeline = Callable[..., Awaitable[PipelineResult]]


class QuoteNotFoundError(KeyError):
    """No quote with that id."""


class ApprovalBlockedError(RuntimeError):
    """FR-083: blocking critic flags must be explicitly waived before approval."""

    def __init__(self, flags: list[str]) -> None:
        super().__init__(f"blocking flags require a waiver: {flags}")
        self.flags = flags


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context_columns(result: PipelineResult) -> dict[str, str]:
    """FR-131 + FR-045: the plan and the recalled memories, persisted with the quote.

    They are stored rather than merely traced because the reviewer needs them at the moment of the
    decision, not in a debugging artifact afterwards. A memory that only a developer can find is a
    memory the business never gets to use.
    """
    # FR-064: what a revision re-drafts from. A quote's document is read exactly once - the bytes
    # are not kept, and for a file drop `source_text` is only a placeholder - so if the extraction
    # is not written down here, there is nothing left to amend later.
    columns: dict[str, str] = {"extraction_json": result.extraction.model_dump_json()}
    if result.plan is not None:
        columns["plan_json"] = result.plan.model_dump_json()
    if result.episodic:
        columns["episodic_json"] = json.dumps(
            {
                "truncated": result.episodic_truncated,
                "recalls": [recall.model_dump(mode="json") for recall in result.episodic],
            }
        )
    return columns


class QuoteService:
    """The only writer of quote state. The API is a thin shell over this."""

    def __init__(
        self,
        *,
        store: QuoteStore,
        facade: MemoryFacade,
        settings: Settings,
        seller_block: dict[str, Any],
        pipeline: Pipeline = quote_from_text,
        excel_pipeline: Pipeline = quote_from_excel,
        pdf_pipeline: Pipeline = quote_from_pdf,
        image_pipeline: Pipeline = quote_from_image,
        revision_pipeline: Pipeline = quote_from_revision,
        artifacts: ArtifactStore | None = None,
    ) -> None:
        self.store = store
        self.facade = facade
        self.settings = settings
        self.seller_block = seller_block
        self.pipeline = pipeline
        self.revision_pipeline = revision_pipeline
        self._artifacts = artifacts

        # FR-021/022/033: which parser runs is decided *here*, once, and both intake channels - the
        # API upload and the OSS drop - go through it.
        #
        # They did not, and why the bug survived is worth recording. Both channels used to do
        # `raw.decode("utf-8", errors="replace")` behind a comment saying PDF and Excel parsing
        # would "land with FR-031/032". Those FRs landed. The comments did not. So a spreadsheet
        # dropped into the inbox was decoded as mojibake, parsed as prose, and parked - while the
        # eval reported 97% on that very file, because the eval calls `quote_from_excel` directly.
        # The harness proved the parsers and never once touched the seam that was broken.
        self._pipelines: dict[DocType, Pipeline] = {
            DocType.EMAIL_TEXT: pipeline,
            DocType.EXCEL: excel_pipeline,
            DocType.PDF_DIGITAL: pdf_pipeline,
            DocType.PDF_SCAN: pdf_pipeline,  # quote_from_pdf decides scan vs digital for itself
            DocType.IMAGE: image_pipeline,
        }

    @property
    def artifacts(self) -> ArtifactStore:
        """OSS is only needed for dispatch, so the client is built lazily."""
        if self._artifacts is None:
            self._artifacts = ArtifactStore.from_settings(self.settings)
        return self._artifacts

    # --- persistence helpers ---
    def _load(self, quote_id: str) -> dict[str, Any]:
        stored = self.store.get_quote(quote_id)
        if stored is None:
            raise QuoteNotFoundError(quote_id)
        return stored

    def _transition(
        self,
        record: QuoteRecord,
        target: Status,
        actor: Actor,
        event: str,
        payload: dict[str, Any] | None = None,
        **columns: Any,
    ) -> QuoteRecord:
        assert_transition(record.status, target)  # FR-080: illegal transitions raise
        record.status = target
        record.updated_at = _now()
        record.actor_last = actor.name or actor.kind
        self.store.put_quote(record, **columns)
        self.store.append_audit(record.quote_id, actor=actor, event=event, payload_json=payload)
        return record

    # --- intake (FR-020, FR-022, FR-024) ---
    def submit(
        self,
        *,
        text: str,
        digest_payload: bytes | str | None = None,
        channel: Channel = Channel.PASTE,
        filename: str | None = None,
        customer_hint: str | None = None,
        email_meta: EmailMeta | None = None,
        source_uri: str | None = None,
        on_date: date_type | None = None,
    ) -> tuple[QuoteRecord, bool]:
        """Register an RFQ -> (record, created). A re-post of the same bytes is not a new quote.

        `digest_payload` is what FR-024 deduplicates on, and for a file it must be the file's own
        bytes. `text` is only what a human sees on the record: for a binary drop it is a
        placeholder, and hashing *that* would mean two different spreadsheets sharing a filename
        collapsed into one quote, while the same spreadsheet renamed became two.
        """
        digest = payload_hash(text if digest_payload is None else digest_payload)
        existing_id = self.store.get_idempotency(digest)
        if existing_id is not None:  # FR-024
            return self._load(existing_id)["record"], False

        intake = classify(text=text, filename=filename, email_meta=email_meta)
        today = on_date or date_type.today()
        sequence = self.store.next_sequence(today.year)  # FR-062: atomic per-year counter

        record = QuoteRecord(
            quote_id=new_ulid(),
            quote_number=format_quote_number(today.year, sequence),
            status=Status.RECEIVED,
            channel=channel,
            source_uri=source_uri,
            language=intake.language,
            sha256_payload=digest,
            actor_last="system",
        )
        self.store.put_quote(record, source_text=text)
        self.store.put_idempotency(digest, record.quote_id)
        self.store.append_audit(
            record.quote_id,
            actor=SYSTEM,
            event="intake.received",
            payload_json={
                "channel": channel.value,
                "doc_type": intake.doc_type.value,
                "language": intake.language.value,
                "urgency": intake.urgency.value,
                "customer_hint": customer_hint,
            },
        )
        return record, True

    # --- the pipeline, persisted stage by stage ---
    async def process(
        self,
        record: QuoteRecord,
        payload: str | bytes,
        *,
        doc_type: DocType = DocType.EMAIL_TEXT,
        customer_hint: str | None = None,
        customer_email: str | None = None,
        on_date: date_type | None = None,
    ) -> QuoteRecord:
        """Run the pipeline for this document type, persisting each stage.

        `payload` is text for an email or paste, and raw bytes for a spreadsheet, PDF or image.
        Ends at pending_approval or a durable failure state.
        """
        record = self._transition(record, Status.PARSING, PIPELINE, "pipeline.parsing")
        _, sequence = parse_quote_number(record.quote_number)
        tracer = Tracer(record.quote_id, include_content=self.settings.trace_content)
        pipeline = self._pipelines[doc_type]

        try:
            result = await pipeline(
                payload,
                settings=self.settings,
                facade=self.facade,
                seller_block=self.seller_block,
                sequence=sequence,
                on_date=on_date,
                customer_email=customer_email,
                customer_hint=customer_hint,
                tracer=tracer,
            )
        except Exception as exc:  # noqa: BLE001 - any pipeline failure must land in a durable state
            return self._transition(
                record,
                Status.FAILED_PARSE,
                SYSTEM,
                "pipeline.failed",
                {"error": f"{type(exc).__name__}: {exc}"},
            )

        trace_json = self._persist_trace(record, result)

        if result.clarification_reasons:  # FR-034
            return self._transition(
                record,
                Status.NEEDS_CLARIFICATION,
                PIPELINE,
                "pipeline.needs_clarification",
                {"reasons": result.clarification_reasons},
                trace_json=trace_json,
            )

        if result.resolution is not None and result.resolution.profile is not None:
            record.customer_id = result.resolution.profile.customer_id

        record = self._transition(
            record,
            Status.MATCHING,
            PIPELINE,
            "pipeline.matched",
            {
                "matches": [
                    {"line": m.line_ref, "sku": m.sku, "status": m.status.value}
                    for m in result.matches
                ]
            },
        )
        quote = result.quote
        critic = result.critic
        assert quote is not None and critic is not None  # guaranteed when there are no reasons

        quote_json = quote.model_dump_json()
        record = self._transition(
            record,
            Status.PRICING,
            PIPELINE,
            "pipeline.priced",
            {"subtotal_vnd": quote.subtotal_vnd, "total_vnd": quote.total_vnd},
        )
        record = self._transition(record, Status.DRAFTING, PIPELINE, "pipeline.drafted")
        record = self._transition(record, Status.VALIDATING, PIPELINE, "pipeline.validating")

        record.flags = [*critic.blocking, *critic.non_blocking]
        record.totals_json = totals_of(quote_json)

        # FR-070: a recompute mismatch is a hard failure - the arithmetic did not survive an
        # independent check, so the draft is rejected outright. Policy flags (FR-071) are different:
        # they still reach the human, who may waive them explicitly at the gate (FR-083).
        if critic.recompute_diffs:
            return self._transition(
                record,
                Status.CRITIC_FAILED,
                PIPELINE,
                "critic.failed",
                {"diffs": [diff.model_dump(mode="json") for diff in critic.recompute_diffs]},
                quote_json=quote_json,
                trace_json=trace_json,
                critic_json=critic.model_dump_json(),
                html=result.html,
                **_context_columns(result),
            )

        return self._transition(
            record,
            Status.PENDING_APPROVAL,
            PIPELINE,
            "pipeline.pending_approval",
            {
                "total_vnd": quote.total_vnd,
                "blocking": critic.blocking,  # the human must waive these to approve
                "non_blocking": critic.non_blocking,
            },
            quote_json=quote_json,
            trace_json=trace_json,
            critic_json=critic.model_dump_json(),
            html=result.html,
            **_context_columns(result),
        )

    def _persist_trace(self, record: QuoteRecord, result: PipelineResult) -> str | None:
        """FR-111: write trace.json to OSS. A trace failure must never fail a quote."""
        if result.trace is None:
            return None
        document = result.trace.model_copy(update={"quote_id": record.quote_id})
        payload = document.model_dump_json()
        try:
            self.artifacts.put_trace(record.quote_id, payload)
        except Exception as exc:  # noqa: BLE001 - observability is never load-bearing
            self.store.append_audit(
                record.quote_id,
                actor=SYSTEM,
                event="trace.persist_failed",
                payload_json={"error": f"{type(exc).__name__}: {exc}"},
            )
        return payload

    def trace(self, quote_id: str) -> dict[str, Any]:
        """API-05: the persisted reasoning trace."""
        stored = self._load(quote_id)
        raw = stored.get("trace_json")
        if not isinstance(raw, str):
            return {"quote_id": quote_id, "steps": []}
        document: dict[str, Any] = json.loads(raw)
        return document

    # --- review payload (FR-082) ---
    def review(self, quote_id: str) -> dict[str, Any]:
        """Everything the reviewer needs on one screen."""
        stored = self._load(quote_id)
        record: QuoteRecord = stored["record"]
        payload: dict[str, Any] = {
            "record": record.model_dump(mode="json"),
            "status": record.status.value,
            "flags": record.flags,
            "totals": record.totals_json,
        }
        for key in ("quote_json", "critic_json", "plan_json", "episodic_json"):
            if key in stored:
                payload[key.removesuffix("_json")] = json.loads(stored[key])
        payload["audit"] = [
            event.model_dump(mode="json") for event in self.store.list_audit(quote_id)
        ]
        return payload

    def queue(self, status: Status | None = None, limit: int = 50) -> list[QuoteRecord]:
        """API-02."""
        return self.store.list_quotes(status=status, limit=limit)

    def stale_pending(self, hours: int = PENDING_REMINDER_HOURS) -> list[QuoteRecord]:
        """FR-085: quotes that have been waiting on a human for too long."""
        cutoff = _now() - timedelta(hours=hours)
        return [
            record
            for record in self.store.list_quotes(status=Status.PENDING_APPROVAL, limit=200)
            if record.updated_at < cutoff
        ]

    # --- the human gate (FR-083, FR-084) ---
    def approve(
        self,
        quote_id: str,
        *,
        comment: str | None = None,
        waive_flags: list[str] | None = None,
        reason: str | None = None,
    ) -> QuoteRecord:
        """FR-083. Blocking flags must be waived explicitly, and the waiver is audited."""
        stored = self._load(quote_id)
        record: QuoteRecord = stored["record"]

        blocking: list[str] = []
        if "critic_json" in stored:
            critic = CriticReport.model_validate_json(stored["critic_json"])
            blocking = critic.blocking
        waived = set(waive_flags or [])
        unwaived = [flag for flag in blocking if flag not in waived]
        if unwaived:
            raise ApprovalBlockedError(unwaived)

        payload: dict[str, Any] = {"comment": comment}
        if waived:
            payload["waived_flags"] = sorted(waived)
            payload["waiver_reason"] = reason
        record = self._transition(record, Status.APPROVED, HUMAN, "human.approved", payload)

        # FR-046 distinguishes an approval from an *edited* approval, and the difference is real: a
        # quote a human had to waive a flag on, or send back for revision first, is a more
        # interesting memory than one they nodded through.
        edited = bool(waived) or record.revision > 0
        self._remember(
            record,
            stored,
            Outcome.EDITED if edited else Outcome.APPROVED,
            human_edits=reason or comment,
        )
        return record

    def _remember(
        self,
        record: QuoteRecord,
        stored: dict[str, Any],
        outcome: Outcome,
        *,
        human_edits: str | None,
    ) -> None:
        """FR-044: write the episode the human just decided.

        Never raises. The human's decision is the thing that matters and it is already durably
        recorded on the audit chain; losing a *memory* of it must not lose the decision itself. A
        failed write is logged and the approval stands.
        """
        if record.customer_id is None or "quote_json" not in stored:
            return  # nothing to attribute the memory to, or no quote was ever produced
        try:
            write_episode(
                facade=self.facade,
                settings=self.settings,
                quote=Quote.model_validate_json(stored["quote_json"]),
                customer_id=record.customer_id,
                outcome=outcome,
                human_edits=human_edits,
            )
        except Exception as exc:  # noqa: BLE001 - a memory must never cost us a decision
            log_event(
                "episodic_write_failed",
                level=logging.WARNING,
                quote_id=record.quote_id,
                error=f"{type(exc).__name__}: {exc}",
            )

    # --- dispatch (FR-090..094) ---
    def quote_of(self, quote_id: str) -> Quote:
        """The stored Quote aggregate. Raises if the pipeline never produced one."""
        stored = self._load(quote_id)
        raw = stored.get("quote_json")
        if not isinstance(raw, str):
            raise QuoteNotFoundError(f"{quote_id} has no quote yet")
        return Quote.model_validate_json(raw)

    def pdf_url(self, quote_id: str) -> str:
        """API-09 / FR-091: a fresh presigned GET, rendering and storing the PDF if needed."""
        quote = self.quote_of(quote_id)
        key = artifact_key(quote.quote_number)
        if not self.artifacts.exists(key):
            self.artifacts.put_pdf(quote.quote_number, self._render(quote))
        return self.artifacts.presigned_get(key)

    def _render(self, quote: Quote) -> bytes:
        note = vat_policy_note(date_type.fromisoformat(quote.date))
        return render_pdf(quote, vat_policy_note=note)

    def recipient_of(self, quote_id: str) -> str | None:
        """Who this quote would be sent to, if anyone.

        An RFQ dropped as a file into OSS carries no sender - there is no email on it, because
        nobody attached one. That is a perfectly ordinary state, and the caller needs to know it
        *before* approving rather than discovering it as a failure afterwards.
        """
        email = self.quote_of(quote_id).customer_block.get("email")
        return email if isinstance(email, str) and email else None

    def dispatch(self, quote_id: str, *, recipient: str | None = None) -> QuoteRecord:
        """FR-090..093: render, store privately, presign, and send. Every step is audited.

        A quote with no recipient is NOT dispatched and is NOT a failure. It used to be: approval
        scheduled a dispatch, the dispatch found no address, and an approved quote landed in
        `failed_dispatch` - which reads, to a human, as though the system broke. It had not:
        nobody had told it where to send the thing. The approval stands, the quote stays `approved`,
        and the skip goes on the audit trail with its reason, so a person can supply an address.
        """
        stored = self._load(quote_id)
        record: QuoteRecord = stored["record"]
        quote = self.quote_of(quote_id)

        to = recipient or quote.customer_block.get("email")
        if not isinstance(to, str) or not to:
            self.store.append_audit(
                record.quote_id,
                actor=SYSTEM,
                event="dispatch.skipped",
                payload_json={"reason": "no recipient on the quote; approval stands"},
            )
            return record

        record = self._transition(record, Status.DISPATCHING, SYSTEM, "dispatch.started")

        try:
            pdf = self._render(quote)
            key = self.artifacts.put_pdf(quote.quote_number, pdf)  # FR-091: private object
            link = self.artifacts.presigned_get(key)

            result = send_quote(  # FR-092 / FR-093
                quote,
                settings=self.settings,
                artifacts=self.artifacts,
                seller_name=str(self.seller_block.get("name", "CyberSkill")),
                recipient=to,
                link=link,
                contact=quote.customer_block.get("contact"),
                pdf=pdf,
            )
        except Exception as exc:  # noqa: BLE001 - a failed dispatch must land in a durable state
            return self._transition(
                record,
                Status.FAILED_DISPATCH,
                SYSTEM,
                "dispatch.failed",
                {"error": f"{type(exc).__name__}: {exc}"},
            )

        event = "dispatch.sent" if result.transport == "smtp" else "dispatch.sent_stub"
        return self._transition(
            record,
            Status.SENT,
            SYSTEM,
            event,
            {
                "transport": result.transport,
                "message_id": result.message_id,
                "recipient": result.recipient,
                "pdf_key": key,
                "attached": result.attached,
                "outbox_key": result.outbox_key,
            },
        )

    def reject(self, quote_id: str, *, comment: str | None = None) -> QuoteRecord:
        stored = self._load(quote_id)
        record: QuoteRecord = stored["record"]
        record = self._transition(
            record, Status.REJECTED, HUMAN, "human.rejected", {"comment": comment}
        )
        # FR-044/046: a rejection is the *most* important thing to remember (importance 0.9). It is
        # the only signal that says this quote, for this customer, was wrong.
        self._remember(record, stored, Outcome.REJECTED, human_edits=comment)
        return record

    async def revise(
        self, quote_id: str, *, instruction: str, on_date: date_type | None = None
    ) -> QuoteRecord:
        """FR-064/FR-084: re-draft honouring the instruction. After MAX_REVISIONS a human takes it.

        The re-draft starts from the stored *extraction*, not from the source document, because for
        every channel except a pasted email there is no source document to start from: the bytes
        were never kept, and `source_text` is a placeholder a human can read.

        This used to concatenate the instruction onto that placeholder and re-run the text pipeline.
        For a quote that arrived as a spreadsheet, a PDF or a photo, that fed the parser a string
        with no line items in it - so asking for a 3% discount handed back a quote with nothing on
        it. Every test passed, because every test revised a quote that had been pasted as text.
        """
        stored = self._load(quote_id)
        record: QuoteRecord = stored["record"]
        record = self._transition(
            record, Status.REVISING, HUMAN, "human.revise", {"instruction": instruction}
        )

        record.revision += 1
        if record.revision > MAX_REVISIONS:  # FR-064
            return self._transition(
                record,
                Status.NEEDS_MANUAL,
                SYSTEM,
                "revision.limit_reached",
                {"revision": record.revision},
            )

        raw_extraction = stored.get("extraction_json")
        if not raw_extraction:
            # A quote stored before extraction_json existed, or one that never got past parsing.
            # There is nothing to amend, and guessing from a placeholder is what caused the bug.
            return self._transition(
                record,
                Status.NEEDS_MANUAL,
                SYSTEM,
                "revision.no_extraction",
                {"reason": "the quote has no stored extraction to re-draft from"},
            )

        _, sequence = parse_quote_number(record.quote_number)
        result = await self.revision_pipeline(
            RFQExtraction.model_validate_json(raw_extraction),
            instruction,
            settings=self.settings,
            facade=self.facade,
            seller_block=self.seller_block,
            sequence=sequence,
            on_date=on_date,
        )
        if result.quote is None or result.critic is None:
            return self._transition(
                record,
                Status.NEEDS_MANUAL,
                SYSTEM,
                "revision.failed",
                {"reasons": result.clarification_reasons},
            )

        record = self._transition(record, Status.DRAFTING, PIPELINE, "revision.drafted")
        record = self._transition(record, Status.VALIDATING, PIPELINE, "revision.validating")
        record.flags = [*result.critic.blocking, *result.critic.non_blocking]
        record.totals_json = totals_of(result.quote.model_dump_json())
        return self._transition(
            record,
            Status.PENDING_APPROVAL,
            PIPELINE,
            "revision.pending_approval",
            {"revision": record.revision, "total_vnd": result.quote.total_vnd},
            quote_json=result.quote.model_dump_json(),
            critic_json=result.critic.model_dump_json(),
            html=result.html,
            # The amended extraction replaces the original, so a *second* revision builds on the
            # first rather than silently reverting it.
            **_context_columns(result),
        )
