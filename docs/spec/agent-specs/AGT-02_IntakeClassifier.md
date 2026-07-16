# AGT-02 — IntakeClassifier — Agent Behavior Specification

**Document ID:** QM-AGT-02 · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6 (AGT-02), TASK-022/023/043
**Implements in:** `src/quotemind/agents/intake.py` · **Prompt file:** `src/quotemind/prompts/intake.md`

---

## 1. Mission

Classify one inbound RFQ in a single cheap pass: language, document type, urgency, and (via tool) customer identity. Produce `IntakeResult` (DM-02) so the router can pick the right parser and the pipeline can apply the right tier. Never extract line items; never guess customers without the lookup tool.

## 2. Construction (normative)

```python
def build_intake() -> ReActAgent:
    return ReActAgent(
        name="IntakeClassifier",
        sys_prompt=load_prompt("intake"),
        model=DashScopeChatModel(
            model_name=MODEL_CLASSIFIER,       # qwen-plus
            api_key=settings.DASHSCOPE_API_KEY,
            stream=False,
            enable_thinking=False,
        ),
        formatter=DashScopeChatFormatter(),
        toolkit=build_toolkit("intake"),
        memory=InMemoryMemory(),
        max_iters=4,
    )
```

Generation params: temperature 0.0. Output is obtained with `structured_model=IntakeResult` — the call site asserts `res.metadata` validates.

## 3. Input contract

The agent receives one `Msg(role="user")` assembled by code containing:
- For text channel: the raw email text (truncated to 6,000 chars; remainder noted as `[truncated N chars]`).
- For file channels: filename, size, magic-sniffed mime, first-page thumbnail description is NOT provided (classification of pdf_digital vs pdf_scan is done in code by text-layer probe: pypdfium2 extractable-text ratio ≥ 0.2 ⇒ digital). The agent classifies language/urgency from filename + any body text; doc_type arrives pre-filled and the agent must echo it unchanged.
- `email_meta` (from, subject, date) when present (TASK-023).

## 4. Tools available

| Tool | Signature | Behavior |
|---|---|---|
| `lookup_customer` | `(email_domain: str | None, name_hint: str | None) -> ToolResponse` | KnowledgeStore `customers` tenant: exact domain match first, then FTS name fuzzy; returns `{customer_id, name, tier, confidence, method}` or `{customer_id: null}` |

Exactly one tool. The agent must call it at most twice (domain attempt, then name attempt) per run.

## 5. Normative system prompt (`prompts/intake.md` v1.0)

```
<!-- prompt: intake | version: 1.0 | agent: AGT-02 | spec: QM-SPEC-001 -->
Classify this inbound request-for-quotation. Return ONLY the structured object.

Determine:
- language: "vi" | "en" | "mixed" — judge by the language of the actual request
  body, not the signature or boilerplate. mixed only when substantive request
  content appears in both languages.
- doc_type: echo the provided doc_type field exactly; never change it.
- urgency: "urgent" if the request contains gấp, khẩn, khẩn cấp, sớm nhất,
  urgent, ASAP, as soon as possible, by tomorrow, trong hôm nay; else "normal".
- customer_match: call lookup_customer with the sender email domain first; if
  no match and a company name is visible in the text or signature, call it once
  more with that name. Report exactly what the tool returned, including its
  confidence and method. If the tool returns null, customer_id is null.

Never invent a customer. Never extract products, quantities, or prices — that
is another agent's job. If the text is empty or clearly not an RFQ, still
return the object with your best language guess and note "not_rfq" in notes.
```

## 6. Output contract — `IntakeResult` (DM-02)

```python
class CustomerMatch(BaseModel):
    customer_id: str | None
    method: Literal["domain", "name_fts", "hint", "none"]
    confidence: float = Field(ge=0, le=1)

class IntakeResult(BaseModel):
    language: Literal["vi", "en", "mixed"]
    doc_type: Literal["email_text", "pdf_digital", "pdf_scan", "image", "xlsx"]
    urgency: Literal["normal", "urgent"]
    customer_match: CustomerMatch
    notes: str | None = None      # e.g. "not_rfq"
```

## 7. Guardrails

1. `max_iters=4`; the run is expected to complete in ≤3 (reason → tool → answer).
2. Code-side validation rejects any doc_type differing from the pre-filled value (echo check) → error PARSE routing bug, not agent retry.
3. `lookup_customer` call count enforced ≤2 by tool middleware; a third call returns an error instructing the agent to answer.
4. `not_rfq` note does NOT stop the pipeline by itself; TASK-034's empty-extraction gate is the authoritative stop. (Keeps false negatives cheap.)
5. PII: the agent sees sender email; it must copy only the domain into narration, never the full address (full address lives in the stored email_meta only).

## 8. Failure handling

| Event | Action |
|---|---|
| structured_model validation fails | one retry with validation errors appended; then FAILED_INTAKE |
| lookup tool error | proceed with customer_id null, method "none", confidence 0 |
| Empty input text and no file | FAILED_INTAKE, reason `EMPTY_PAYLOAD` (TASK-025) |

## 9. Observability

Spans: `invoke_agent IntakeClassifier`, `chat qwen-plus`, `execute_tool lookup_customer`. Trace step summary format: `"vi · email_text · normal · customer=cust_thanhcong (domain, 0.98)"`.

## 10. Evaluation criteria

| Metric | Target | Method |
|---|---|---|
| Language accuracy | 100% on eval set | EV-04 labels |
| doc_type echo integrity | 100% | trace assertion |
| Urgency keyword recall | 100% on seeded urgent cases (3 in set) | EV-04 |
| Customer resolution accuracy | ≥ 95% on labeled cases; zero invented customers | EV-04 |
| Cost | ≤ $0.002 per classification | TASK-112 accounting |

*End QM-AGT-02 v1.0.0.*
