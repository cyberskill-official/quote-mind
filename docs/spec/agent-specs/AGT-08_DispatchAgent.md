# AGT-08 — DispatchAgent — Agent Behavior Specification

**Document ID:** QM-AGT-08 · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6 (AGT-08), FR-090..094, FR-044
**Implements in:** `src/quotemind/agents/dispatch.py` + `tools/dispatch_tools.py` · **Prompt file:** `src/quotemind/prompts/dispatch_email.md`

---

## 1. Mission

Turn an approved quote into delivered artifacts: render the bilingual PDF, store it, presign the link, send the email, write the episodic memory, and close the audit trail. Code-first: the only LLM contribution is the short courtesy text of the email body. Runs exclusively from status `approved`; exactly once per quote.

## 2. Execution sequence (code, normative)

```
approved
  │ 1. render_pdf(quote)            # Jinja2 template_quote.html.j2 → WeasyPrint → bytes
  │ 2. store_artifact(pdf)          # oss://quotemind-artifacts/quotes/{quote_number}.pdf
  │ 3. presign(key, 600s)           # V4, slash_safe=True
  │ 4. compose_email(quote)         # LLM courtesy text (≤120 words) into fixed template
  │ 5. send_email(...)              # DirectMail SMTP 465, or stub → outbox/{quote_number}.eml
  │ 6. write_episodic(quote)        # FR-044: summary, items, outcome, importance init
  │ 7. audit_close(message_id)      # AuditEvent chain
  ▼
sent   (any step failure → failed_dispatch with step name; steps 1–3 retryable, 5 idempotent-guarded)
```

State transitions `approved → dispatching → sent | failed_dispatch` via guarded `set_quote_state`.

## 3. PDF rendering contract (FR-090, Appendix C)

- Template `quote/render/template_quote.html.j2` + `quote.css` implement Appendix C exactly: A4, 18 mm margins, Umber header band, bilingual table columns, per-rate VAT lines, bằng chữ, terms grid, bank block, signature row, footer with vat_policy_note + FX note + `Trang/Page X/Y`.
- Fonts: bundled `BeVietnamPro-{Regular,SemiBold,Bold}.ttf` via `@font-face { src: url(...) }` (never `local()`); `FontConfiguration()` passed to `write_pdf`.
- Internal-only fields (margin) are excluded by the template context builder, not by template logic — the renderer receives a customer-safe projection.
- Render environment: FC layer with Pango/Cairo; fallback `deploy/Dockerfile.pdf` container (repo blueprint). Golden pixel-diff test guards drift (FR-124).

## 4. Email contract (FR-092/093)

Fixed bilingual skeleton (code) with one LLM slot:

```
Subject: Báo giá / Quotation {quote_number} — {seller_short}
[vi greeting with customer name]
{LLM courtesy paragraph, ≤120 words total across both languages}
- Link tải báo giá (hiệu lực {presign_minutes} phút) / Download link (valid {presign_minutes} min): {url}
- Hiệu lực báo giá / Quote validity: {validity_days} ngày/days
[fixed vi/en closing + seller signature block]
```

Attachment: PDF attached when ≤3 MB, else link-only. Transport: `MAIL_TRANSPORT=smtp` → DirectMail SSL 465 with `DIRECTMAIL_USER/PASSWORD`; `stub` → RFC-822 `.eml` written to `oss://quotemind-artifacts/outbox/`, audited `sent_stub`. Message-Id (or stub key) recorded.

LLM slot construction: `MODEL_DRAFTER` at temp 0.2, prompt `dispatch_email.md`:

```
<!-- prompt: dispatch_email | version: 1.0 | agent: AGT-08 | spec: QM-SPEC-001 -->
Write the short courtesy paragraph for the quote delivery email, Vietnamese
first then English, together at most 120 words. Thank the customer for the
request, state the quotation {quote_number} is attached/linked, mention the
validity of {validity_days} days, and invite questions to {seller_email}.
No prices, no product details, no superlatives, no promises beyond the quote.
```

Code lint on the slot: reject if it contains any digit-currency pattern or SKU (same regex as AGT-06 guardrail); one retry then fall back to a fixed template paragraph (never block dispatch on the LLM).

## 5. Episodic memory write (FR-044, this agent's responsibility)

After send: build `EpisodicQuoteMemory` — bilingual summary via `MODEL_DRAFTER` (≤120 words, prompt inline, same lint), items_brief from priced lines, outcome (approved/edited: edited when revision>0 or waivers present; the rejected path writes its memory from the reject handler, not here), human_edits = concatenated revision instructions, importance initial per FR-046 (approved 0.7 / edited 0.8 [+0.1 if total > 100M VND, cap 1.0]), embedding of summary. Tenant `episodic:{customer_id}`; skipped with flag `EPISODIC_SKIPPED_UNKNOWN_CUSTOMER` when customer_id is null.

## 6. Guardrails

1. Entry-state check: any status ≠ approved → refuse (guarded transition), audit `DISPATCH_REFUSED_STATE`.
2. Single-send: conditional update on `qm_quotes` (status approved→dispatching) is the mutex; a concurrent second call loses the conditional write and exits idempotently. Send step also checks an audit marker before SMTP.
3. LLM output lint (no numbers/SKUs) with template fallback — dispatch never blocks on model quality.
4. Presign TTL ≤ 600 s (NFR-006); the email states the TTL; `GET /api/quotes/{id}/pdf` re-presigns for later access.
5. No customer PII in logs beyond domain + quote_number (log scrubber).

## 7. Failure handling

| Event | Action |
|---|---|
| Render fails | retry ×1; failed_dispatch `RENDER_FAIL` (golden test makes this near-impossible) |
| OSS put/presign fails | retry ×2 backoff; failed_dispatch `STORE_FAIL` |
| SMTP fails | retry ×2; then automatic stub fallback with flag `SMTP_FELL_BACK_TO_STUB` (demo continuity) |
| Episodic write fails | quote still `sent`; flag `EPISODIC_WRITE_FAIL` (memory is best-effort post-send) |

## 8. Observability

Spans: `invoke_agent DispatchAgent`, `execute_tool render_pdf` (duration, `qm.pdf_kb`), `execute_tool send_email` (`qm.transport`), `chat qwen3-max` for the slot, memory write span. Summary: `"PDF 214 KB · presigned 600s · sent via stub · episodic written (importance 0.8)"`.

## 9. Evaluation criteria

| Metric | Target | Method |
|---|---|---|
| Dispatch success on EV-04 approvals | 100% (stub) | EV-04 |
| Golden PDF pixel-diff | ≤ 2% | FR-124 |
| Diacritics in rendered PDF copy-paste | byte-exact | EV-04 sampled |
| Single-send under concurrent approve race | exactly one send | EV-07 |
| Email lint violations shipped | 0 (fallback engages) | trace |

*End QM-AGT-08 v1.0.0. This completes the eight-sheet pack QM-AGT-01..08.*
