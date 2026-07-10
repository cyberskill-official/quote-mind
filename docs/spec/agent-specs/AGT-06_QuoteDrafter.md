# AGT-06 — QuoteDrafter — Agent Behavior Specification

**Document ID:** QM-AGT-06 · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6 (AGT-06), FR-060..065, FR-045/048/049
**Implements in:** `src/quotemind/agents/drafter.py` + `src/quotemind/quote/assemble.py` · **Prompt file:** `src/quotemind/prompts/drafter.md`

---

## 1. Mission

Write the human language of the quote — bilingual notes, terms, substitution explanations, opening and closing — around numbers that are injected read-only from the PricingEngine. Ground terms in SOP memory and reference episodic memories naturally. The drafter is the voice; it is never the calculator.

## 2. Division of labor with `quote/assemble.py` (critical design)

Code assembles the numeric skeleton FIRST (FR-060):

```python
skeleton = assemble_skeleton(priced_quote, customer, seller_block, quote_number, today)
# skeleton: DM-10 Quote with ALL numeric + enum fields final, and every
# BilingualText field set to None. checksum = sha256(canonical_numeric_view)
```

The drafter is then invoked with the skeleton (numbers visible, immutable) plus context, and returns ONLY the language fields via `structured_model=QuoteLanguage` (a Pydantic model mirroring just the BilingualText slots + per-line notes). Code merges language into skeleton and re-verifies the checksum — if any numeric drifted (it cannot, by construction, but defense in depth), discard and retry once, then FAILED_DRAFT.

This design makes FR-060's acceptance criterion ("every numeric field equals engine output exactly") true by construction, not by prompt obedience.

## 3. Construction (normative)

```python
def build_drafter() -> ReActAgent:
    return ReActAgent(
        name="QuoteDrafter",
        sys_prompt=load_prompt("drafter"),
        model=DashScopeChatModel(
            model_name=MODEL_DRAFTER,          # qwen3-max
            api_key=settings.DASHSCOPE_API_KEY,
            stream=False, enable_thinking=False,
        ),
        formatter=DashScopeChatFormatter(),
        toolkit=build_toolkit("drafter"),
        memory=InMemoryMemory(),
        max_iters=6,
    )
```

Generation params: temperature 0.3 (the one creative agent), top_p default.

## 4. Context assembly (code, budgeted — FR-045/048/049)

Injected into the user message, in order, under the 2500-token memory budget:
1. The numeric skeleton (rendered compactly).
2. `MatchResult` reasons for flagged lines.
3. Top-3 episodic memories for the customer (effective score = similarity × 0.5^(age_days/90) × importance), each rendered `[QM-2026-0007 · 2026-03-14 · approved] summary...`, hard cap 1200 tokens.
4. Top-2 SOP snippets per needed topic (payment, delivery, warranty, validity, substitution when flags exist).
5. Revision instruction verbatim, when present (FR-064), prefixed `HUMAN INSTRUCTION (authoritative):`.
Overflow drops lowest-effective-score episodic items first, then extra SOPs, logging `memory_truncated=true`.

## 5. Tools available

| Tool | Signature | Behavior |
|---|---|---|
| `get_sop` | `(topic: str) -> ToolResponse` | One more SOP snippet if a needed topic wasn't pre-injected; ≤2 calls |
| `get_episodic` | `(query: str) -> ToolResponse` | One targeted episodic retrieval (e.g. checking a remembered substitution); ≤1 call |

Pre-injection covers the normal case; tools exist for the agent to fill gaps it can articulate. Middleware enforces the call caps.

## 6. Normative system prompt (`prompts/drafter.md` v1.0)

```
<!-- prompt: drafter | version: 1.0 | agent: AGT-06 | spec: QM-SPEC-001 -->
Draft the customer-facing language of this quotation in Vietnamese and English.
You receive the fully priced quote skeleton; every number, SKU, quantity, price,
VAT amount and total is FINAL. You never restate a number differently than
written, never compute, never round. Your output contains only language fields.

Write, as BilingualText (vi first, then a faithful — not literal — en):
- opening_note: 1–2 sentences acknowledging the request (name the customer's
  company), stating the quote covers the requested items.
- per-line note for every flagged line: substitution or spec difference
  (name requested vs offered and the difference), lead time when the item is
  out of stock, or "cần xác nhận / needs confirmation" context. Unflagged
  lines get no note.
- terms.payment / terms.delivery / terms.warranty: ground these in the SOP
  snippets provided; adapt numbers of days or percentages ONLY if the human
  instruction says so; otherwise use SOP defaults verbatim in meaning.
- closing_note: validity restatement ("Báo giá có hiệu lực {n} ngày...") and a
  professional sign-off, no marketing superlatives.
- If episodic memories are provided and relevant, reference precedent naturally
  and specifically: "như báo giá QM-2026-0007 ngày 14/03, quý công ty đã chấp
  nhận thay thế..." — cite the quote number. Never invent history.

Register: Vietnamese trang trọng business style, full diacritics; English plain
professional. HUMAN INSTRUCTION lines are authoritative over everything except
the numbers, which remain untouchable.
```

## 7. Output contract — `QuoteLanguage`

```python
class LineNote(BaseModel):
    line_ref: int
    note: BilingualText

class QuoteLanguage(BaseModel):
    opening_note: BilingualText
    line_notes: list[LineNote]          # exactly the flagged lines, no extras
    terms_payment: BilingualText
    terms_delivery: BilingualText
    terms_warranty: BilingualText
    closing_note: BilingualText
    memory_citations: list[str] = []    # quote numbers actually referenced
```

Code validation: `line_notes.line_ref ⊆ flagged_refs` (extras dropped with warn; missing flagged notes → one retry then FAILED_DRAFT); `memory_citations ⊆ injected memory quote numbers` (hallucinated citation → strip + flag `CITATION_INVALID`, non-blocking, critic will see).

## 8. Guardrails

1. Numeric immutability by construction (§2) + checksum re-verify.
2. Memory citation set-membership (code, §7).
3. Language completeness: every BilingualText must have both vi and en non-empty; enforced by Pydantic validators.
4. Banned-content lint (code): drafter output rejected if it contains digits-with-currency patterns not present in the skeleton (regex `\d[\d\.,]*\s*(đ|VND|USD|\$)`) — prevents the model writing its own prices inside notes.
5. Revision loop: `revision` counter checked by caller; drafter itself is stateless per call.

## 9. Failure handling

| Event | Action |
|---|---|
| structured_model invalid / missing flagged note / banned pattern | 1 retry with the specific violation quoted; then FAILED_DRAFT |
| Tool errors | proceed with pre-injected context only, flag `SOP_TOOL_UNAVAILABLE` |
| Checksum mismatch after merge | discard, retry once, then FAILED_DRAFT (should be impossible; alarms loudly) |

## 10. Observability

Spans: `invoke_agent QuoteDrafter`, `chat qwen3-max`, tool spans. Trace records `memory_citations`, `memory_truncated`, tokens, and first-try checksum pass boolean (feeds the AGT-06 eval metric). Summary: `"draft v1 · 2 line notes · cited QM-2026-0007 · checksum ok"`.

## 11. Evaluation criteria

| Metric | Target | Method |
|---|---|---|
| First-try numeric checksum pass | ≥ 95% | trace stats over EV-04 |
| Flagged-line note coverage | 100% | code validation counters |
| Hallucinated citation rate | 0 blocking (stripped) and ≤ 5% attempted | trace |
| Language quality (EV-06 rubric, vi and en) | ≥ 4/5 average | LLM judge + human spot-check |
| UJ-04 precedent reference present | yes | EV-04 case assertion |

*End QM-AGT-06 v1.0.0.*
