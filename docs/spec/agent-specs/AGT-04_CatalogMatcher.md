# AGT-04 — CatalogMatcher — Agent Behavior Specification

**Document ID:** QM-AGT-04 · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6 (AGT-04), TASK-040..043
**Implements in:** `src/quotemind/agents/matcher.py` · **Prompt file:** `src/quotemind/prompts/matcher.md`

---

## 1. Mission

Resolve every extracted RFQ line to exactly one catalog SKU, or honestly mark it `needs_confirmation` (with alternatives) or `no_match`. The matcher is the pipeline's anti-hallucination chokepoint: it may only select from candidates its retrieval tools return, never from model memory.

## 2. Construction (normative)

```python
def build_matcher() -> ReActAgent:
    return ReActAgent(
        name="CatalogMatcher",
        sys_prompt=load_prompt("matcher"),
        model=DashScopeChatModel(
            model_name=MODEL_DRAFTER,          # qwen3-max (selection reasoning), temp 0.0
            api_key=settings.DASHSCOPE_API_KEY,
            stream=False, enable_thinking=False,
        ),
        formatter=DashScopeChatFormatter(),
        toolkit=build_toolkit("matcher"),
        memory=InMemoryMemory(),
        max_iters=3 + n_lines,                 # bounded by line count
    )
```

Called once per quote with all lines batched (not per line) to allow cross-line reasoning ("items 2 and 3 are the docking station and RAM for the laptop in item 1"), with a hard cap of 25 lines per call; longer RFQs are chunked by code.

## 3. Retrieval pre-pass (code, before the agent runs)

For each line, `tools/catalog_tools.py` executes BOTH retrievals and fuses them; the agent receives ready-made candidate lists (keeps the agent honest and the token bill flat):

1. `KnowledgeStore.vector_search(query_vector=embed(description_normalized + " " + specs_flat), top_k=8, tenant_id="catalog")`
2. `KnowledgeStore.full_text_search(query=description_normalized, tenant_id="catalog", limit=8)`
3. Reciprocal-rank fusion: `score(doc) = Σ 1/(60 + rank_i)`; top 5 fused candidates per line, each rendered as: `sku · name.vi / name.en · key specs · unit · stock_status · lead_time_days` (never prices — pricing is downstream and the matcher must not be price-biased).

Embeddings: `text-embedding-v4`, `dimensions=1024`, batched ≤10 lines per call.

## 4. Tools available to the agent

| Tool | Signature | Behavior |
|---|---|---|
| `get_product` | `(sku: str) -> ToolResponse` | Full CatalogProduct (still without cost_price) for spec verification |
| `search_more` | `(line_ref: int, query: str) -> ToolResponse` | One extra fused retrieval with a reformulated query; max 1 call per line, enforced by middleware |

The candidate lists arrive in the user message; tools exist only for verification and one reformulation.

## 5. Normative system prompt (`prompts/matcher.md` v1.0)

```
<!-- prompt: matcher | version: 1.0 | agent: AGT-04 | spec: QM-SPEC-001 -->
Match each RFQ line to exactly one catalog product, choosing ONLY from the
candidate lists provided (or retrieved via your tools). Return the structured
MatchResult list.

Judgment rules:
- Compare product type, brand, model number, and hard specs (CPU, RAM, storage,
  screen size, license edition and term, port counts). A model-number exact hit
  with compatible specs is a match.
- needs_confirmation when: your best candidate differs from the request in any
  hard spec (e.g. requested RAM 64GB, candidate 32GB), OR the request is generic
  and 2+ candidates fit equally, OR your confidence is below 0.75. Provide up to
  3 alternatives, each with a one-sentence bilingual reason (Vietnamese then
  English) naming the difference.
- no_match when nothing in the candidates is the same product type. Never force
  a laptop onto a tablet request. Preserve the line for human review.
- Related-line reasoning is allowed: accessories may be matched considering the
  main item's brand/model.
- NEVER output a SKU that is not present in the provided or tool-returned
  candidates. Inventing a SKU is the worst possible failure.
- Spec downgrades or substitutions are never silent: they are always
  needs_confirmation with the difference stated.
```

## 6. Output contract — `MatchResult` (DM-09)

```python
class Alternative(BaseModel):
    sku: str
    reason: BilingualText

class MatchResult(BaseModel):
    line_ref: int
    status: Literal["matched", "needs_confirmation", "no_match"]
    sku: str | None
    match_confidence: float = Field(ge=0, le=1)
    alternatives: list[Alternative] = Field(max_length=3, default_factory=list)
    reason: BilingualText | None    # required when needs_confirmation or no_match
```

Code-side post-validation: every returned `sku` and alternative sku must be ∈ union of candidate skus for that line (set check); violation discards the result and retries once with the violation named; second violation → MATCH_FAIL. This check is the guardrail, not the prompt.

## 7. Guardrails

1. SKU set-membership check (above) — hard, code-enforced.
2. `search_more` ≤1 per line (middleware).
3. Confidence calibration rule in code: status `matched` with confidence <0.75 is coerced to `needs_confirmation` (prompt asks for it; code guarantees it).
4. The matcher never sees `cost_price`, `dealer_price`, or `list_price` — price-blind matching (candidates and get_product responses are redacted).
5. Out-of-stock is NOT a match failure; stock_status flows through for TASK-056 lead-time handling.

## 8. Failure handling

| Event | Action |
|---|---|
| structured_model invalid | 1 retry with errors; then MATCH_FAIL |
| SKU membership violation ×2 | MATCH_FAIL |
| Retrieval (Tablestore) error | tool retry ×2 backoff; then MATCH_FAIL `RETRIEVAL_UNAVAILABLE` |
| >25 lines | code chunks; per-chunk results concatenated by line_ref |

## 9. Observability

Spans: `execute_tool vector_search` / `execute_tool full_text_search` (pre-pass, attributed `gen_ai.tool.name`), `chat qwen3-max`, `execute_tool get_product`. Trace summary per quote: `"5 lines → 4 matched · 1 needs_confirmation (line 4: RAM 64GB→32GB)"`. Retrieval hit lists (sku+score) recorded in trace for the demo's memory/retrieval beat.

## 10. Evaluation criteria

| Metric | Target | Method |
|---|---|---|
| Top-1 SKU accuracy (labeled matchable lines) | ≥ 0.90 | EV-04 |
| Invented-SKU rate | 0 | code check counter must be 0 across EV-04 |
| needs_confirmation recall on seeded conflict fixtures | 100% (2 fixtures: RAM conflict, generic monitor) | EV-04 |
| no_match recall on out-of-catalog fixture | 100% (Wacom fixture) | EV-04 |
| Alternatives quality | human spot-check 5 cases, all reasons name a real difference | manual EV-06 style |

*End QM-AGT-04 v1.0.0.*
