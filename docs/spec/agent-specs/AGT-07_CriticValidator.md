# AGT-07 — CriticValidator — Agent Behavior Specification

**Document ID:** QM-AGT-07 · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6 (AGT-07), TASK-070..074
**Implements in:** `src/quotemind/agents/critic.py` · **Prompt file:** `src/quotemind/prompts/critic.md`

---

## 1. Mission

Independently verify the draft before any human sees it: recompute every monetary figure from raw inputs, run policy checks, verify bilingual numeric parity and encoding health, then write a short bilingual review note. The critic's verdicts on money and policy come from code; the LLM contributes only qualitative review and the narrative. A quote reaches `pending_approval` only through this agent.

## 2. Two-layer design (normative)

**Layer 1 — deterministic checks (code, runs first, authoritative):**

| Check | Rule | Failure class |
|---|---|---|
| Recompute (TASK-070) | `pricing.engine.price(...)` re-run from persisted MatchResults + CustomerProfile + config; every line_total, vat_amount, subtotal, total must equal draft exactly (Decimal ==) | blocking `RECOMPUTE_MISMATCH` (→ critic_failed) |
| Margin policy (TASK-071) | any line or blended margin < MARGIN_FLOOR_PCT | blocking `MARGIN_BELOW_FLOOR` (approvable only with waiver) |
| VAT category (TASK-071) | line category vs vat_rate per App. B map | blocking `VAT_CATEGORY_MISMATCH` |
| Mandatory fields (TASK-071) | quote_number, validity, seller MST, customer name, ≥1 priced line, terms present | blocking `MISSING_FIELD:{name}` |
| Bilingual parity (TASK-072) | numbers/SKUs/dates extracted from vi and en fields must be identical sets (regex numeric extraction) | blocking `BILINGUAL_NUMERIC_MISMATCH` |
| Encoding (TASK-072) | no U+FFFD, no mojibake signatures in any text field | blocking `ENCODING_SUSPECT` |
| Term bounds (TASK-071) | validity 7–45 days; payment terms among SOP-known patterns | non-blocking `TERMS_OUT_OF_BOUNDS` |
| Citation validity | memory_citations ⊆ injected set (re-check) | non-blocking `CITATION_INVALID` |
| Carried flags | needs_confirmation / no_match / UNKNOWN_CUSTOMER / QTY_MISSING / LEAD_TIME propagated | non-blocking (surface at HITL) |

**Layer 2 — LLM review (qwen3-max, temp 0.0):** reads the draft + Layer-1 results; checks qualitative items code cannot (tone/register, note faithfulness to match reasons, no marketing superlatives, human-instruction adherence on revisions); writes the bilingual note (≤80 words per language). The LLM CANNOT flip a Layer-1 verdict in either direction; it may add non-blocking observations only.

## 3. Construction

```python
def build_critic() -> ReActAgent:
    return ReActAgent(
        name="CriticValidator",
        sys_prompt=load_prompt("critic"),
        model=DashScopeChatModel(model_name=MODEL_CRITIC,   # qwen3-max
                                 api_key=settings.DASHSCOPE_API_KEY,
                                 stream=False, enable_thinking=False),
        formatter=DashScopeChatFormatter(),
        toolkit=build_toolkit("critic"),
        memory=InMemoryMemory(),
        max_iters=4,
    )
```

Tools: `recompute_quote(quote_id)` (returns Layer-1 result object; the tool runs the code checks so they appear in the trace as this agent's action) and `get_policy()` (config snapshot). Middleware: recompute must be called exactly once before the agent may answer; enforced by requiring its result id inside the structured output.

## 4. Normative system prompt (`prompts/critic.md` v1.0)

```
<!-- prompt: critic | version: 1.0 | agent: AGT-07 | spec: QM-SPEC-001 -->
You are the final reviewer before a human sees this quotation. First call
recompute_quote and read its result: those numeric and policy verdicts are
absolute — you cannot soften a blocking finding or add a numeric finding of
your own.

Then review qualitatively:
- Do line notes faithfully restate the matcher's reasons (no invented specs)?
- Is the Vietnamese register trang trọng and the English professional, with no
  marketing superlatives?
- On a revision, does the draft actually follow the human instruction?
- Any misleading phrasing around substitutions or lead times?

Return the structured CriticReport: passed (true only if recompute passed and
no blocking flags remain), the flag lists exactly as recompute gave them plus
any qualitative non-blocking observations you add (prefix QUAL_), the
recompute result id, and a review note of at most 80 words per language,
Vietnamese first, stating what was checked and the outcome plainly.
```

## 5. Output contract — `CriticReport` (DM-11 extended)

```python
class CriticReport(BaseModel):
    passed: bool
    blocking: list[str]
    non_blocking: list[str]
    recompute_result_id: str          # must match the tool's issued id
    recompute_diffs: list[str] = []   # empty when passed
    note: BilingualText               # ≤80 words per language (validator)
```

Code post-validation: `passed` must equal Layer-1's verdict (LLM cannot override — mismatch is corrected to Layer-1 and flagged `CRITIC_OVERRIDE_ATTEMPT`, non-blocking, logged loudly); `recompute_result_id` must match, else one retry then CRITIC pipeline error.

## 6. Routing after the critic

| Outcome | Next state |
|---|---|
| passed=true, no blocking | `pending_approval` (blocking=false payload) |
| blocking present but waivable (MARGIN_BELOW_FLOOR only) | `pending_approval` with blocking flags; approve requires waiver (TASK-083) |
| RECOMPUTE_MISMATCH / VAT_CATEGORY_MISMATCH / MISSING_FIELD / BILINGUAL_NUMERIC_MISMATCH / ENCODING_SUSPECT | `critic_failed` (never reaches HITL as-is) |
| TASK-074 (P2) formatting-only defect | one drafter revision round, then re-validate; never for money/policy |

## 7. Fault-injection contract (EV-05)

The eval suite tampers 10 drafts (wrong line total, wrong VAT rate, missing MST, en total ≠ vi total, mojibake note, sub-floor margin, invented citation, superlative tone, missing flagged note, validity 90 days) and asserts: 6 blocking catches route to critic_failed or waiver-gated approval, 4 non-blocking are flagged. Catch rate target: 100%.

## 8. Guardrails

1. Layer-1 supremacy (code-corrected verdicts) — the defining guardrail.
2. Exactly-once recompute (middleware + result id).
3. Note length ≤80 words/language (Pydantic validator, word-count).
4. The critic never edits the draft; it only reports. Revision is the drafter's job via routing.
5. Temp 0.0; `max_iters=4`.

## 9. Observability

Spans: `invoke_agent CriticValidator`, `execute_tool recompute_quote` (with `qm.diff_count`, `qm.blocking_count`), `chat qwen3-max`. Summary: `"recompute exact · 1 blocking (MARGIN_BELOW_FLOOR 4.2% < 5%) · 2 non-blocking · note written"`.

## 10. Evaluation criteria

| Metric | Target | Method |
|---|---|---|
| Seeded-fault catch rate | 100% (10/10) | EV-05 |
| False-block rate on clean EV-04 cases | 0 | EV-04 |
| Layer-1/LLM verdict agreement (no override attempts) | ≥ 95% | trace counter |
| Note quality | ≥ 4/5 EV-06 rubric | judge |

*End QM-AGT-07 v1.0.0.*
