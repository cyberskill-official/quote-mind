# AGT-03 — DocumentParser — Agent Behavior Specification

**Document ID:** QM-AGT-03 · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6 (AGT-03), FR-030..036
**Implements in:** `src/quotemind/agents/parser.py` + `src/quotemind/parsing/*` · **Prompt files:** `prompts/parser_text.md`, `prompts/parser_vision.md`

---

## 1. Mission

Turn any supported RFQ payload (email text, digital PDF, scanned PDF, image, xlsx) into one validated `RFQExtraction` (DM-03) with per-line confidence and source spans, preserving Vietnamese diacritics byte-exact and never inventing quantities. The "agent" is a router plus model calls; xlsx is code-only.

## 2. Routing (code, `parsing/router.py`)

| doc_type | Path | Model |
|---|---|---|
| email_text | `parsing/text.py` — one structured call | `MODEL_PARSER_TEXT` (qwen-plus) |
| pdf_digital | pypdfium2 text-layer extract → same as email_text; if text ratio < 0.2 fallback to vision | qwen-plus |
| pdf_scan / image | `parsing/raster.py` → `parsing/vision.py` per page | `MODEL_PARSER_VISION` (qwen-vl-ocr; fallback qwen3-vl-plus per FR-012) |
| xlsx | `parsing/excel.py` openpyxl; LLM only for ambiguous headers | qwen-plus (headers only) |

Rasterization (FR-031): 200 DPI, max 10 pages (page 11+ dropped with flag `PAGES_TRUNCATED`), long edge downscaled to ≤2560 px, PNG to `oss://quotemind-artifacts/pages/{quote_id}/p{n}.png`.

## 3. Construction

Text path uses a plain ReActAgent with zero tools (pure structured extraction):

```python
def build_parser_text() -> ReActAgent:
    return ReActAgent(
        name="DocumentParser",
        sys_prompt=load_prompt("parser_text"),
        model=DashScopeChatModel(model_name=MODEL_PARSER_TEXT,
                                 api_key=settings.DASHSCOPE_API_KEY,
                                 stream=False, enable_thinking=False),
        formatter=DashScopeChatFormatter(),
        toolkit=Toolkit(),                 # intentionally empty
        memory=InMemoryMemory(),
        max_iters=2,
    )
```

Vision path is NOT a ReActAgent: `parsing/vision.py` calls the OpenAI-compatible endpoint directly per page (content array: N image_url items would exceed budget; exactly one page image + instruction per call), because per-page fan-out with deterministic merging is code logic, not agent reasoning. It still emits `invoke_agent DocumentParser` + `chat qwen-vl-ocr` spans so the trace reads uniformly.

Generation params: temperature 0.0 both paths; vision max_tokens 4096 (qwen-vl-ocr default cap).

## 4. Normative prompts

### 4.1 `prompts/parser_text.md` v1.0

```
<!-- prompt: parser_text | version: 1.0 | agent: AGT-03 | spec: QM-SPEC-001 -->
Extract every product/service line item from this request-for-quotation text.
Return ONLY the structured object.

For each line item:
- raw_text: the verbatim source line(s), unchanged, diacritics preserved.
- description_normalized: cleaned product description (brand, model, key specs),
  in the line's own language. Do not translate.
- quantity: the number requested. If unreadable or absent, null. NEVER guess.
- unit: the unit exactly as written (cái, bộ, chiếc, user, license, tháng, pcs...).
  If absent, null.
- specs: key:value pairs you can read (ram: "32GB", size: "27 inch", term: "1 năm").
- requested_delivery: verbatim if stated, else null.
- confidence: 0-1, your certainty that this line is a real requested item with
  correct quantity.
- source_span: start and end character offsets of raw_text in the input.

Also capture buyer fields if visible: company, tax code (MST, 10 or 13 digits),
contact name, email. Numbered lists, bullet lists, and inline sentences all count.
Ignore signatures, disclaimers, and quoted previous emails. If two lines describe
the same item, keep both; do not merge.
```

### 4.2 `prompts/parser_vision.md` v1.0 (per page)

```
<!-- prompt: parser_vision | version: 1.0 | agent: AGT-03 | spec: QM-SPEC-001 -->
You are reading page {page}/{total} of a Vietnamese or English request-for-
quotation (may be scanned, skewed, or stamped). Extract every product line item
visible on THIS page.

For each: raw_text (verbatim, preserve ALL Vietnamese diacritics exactly),
description_normalized, quantity (number or null — never guess unreadable
numbers), unit (verbatim), specs (key:value), requested_delivery if stated,
confidence 0-1, and source_span as {"page": {page}, "start": 0, "end": 0}
(offsets unknown in vision; keep zeros, page is what matters).

Also capture buyer identity fields if visible on this page: company, MST tax
code, contact, email. Tables: one item per row; the STT/No. column is ordinal,
not quantity — quantity is the SL/Số lượng/Qty column.

Return ONLY a fenced ```json object matching the RFQExtraction schema (lines
may be empty if this page has none).
```

## 5. Merge and validation (code, deterministic)

1. Per-page JSON parsed (fence-stripped); page failures logged, run continues (NFR-004) with flag `PAGE_PARSE_FAIL:{n}`.
2. Merge: concatenate lines in page order; dedupe rule — two lines duplicate iff `normalize(description) == normalize(description)` (NFC, casefold, whitespace-collapse) AND quantity equal; keep first, record `merged_from`.
3. Buyer fields: first non-null wins per field across pages; conflicts flagged `BUYER_FIELD_CONFLICT`.
4. Unit normalization map applied (`cái/chiếc→cái` class kept original in `unit_original`); unknown units pass through.
5. Gate FR-034: zero lines, or any line with null description → `needs_clarification` (`NO_LINE_ITEMS` / `LINE_MISSING_FIELDS`). Null quantity is allowed through with confidence forced ≤0.5 and flag `QTY_MISSING` (HITL will see it).
6. MST validation: 10 or 13 digits pattern; invalid → keep raw, flag `MST_INVALID`.

## 6. Excel path specifics (FR-033)

Header row detection: scan first 10 rows for the row maximizing fuzzy hits against {stt, no, tên hàng, mô tả, description, item, sl, số lượng, qty, quantity, đvt, unit, đơn vị}; ratio ≥ 0.5 required, else LLM sees only the candidate header rows (never numeric cells) to pick one. Data rows read typed: quantity from cell value (int/float→Decimal), never from LLM. Merged cells unmerged forward-fill on description column only.

## 7. Guardrails

1. Vision calls per quote ≤ 10 (page cap) + 1 retry each max.
2. JSON repair: one attempt with a "return only valid JSON" reminder; second failure → page fail flag.
3. Diacritics integrity: post-merge, assert extraction contains no U+FFFD and no mojibake signature (`Ã.`, `á»`), else flag `ENCODING_SUSPECT` (blocking at critic).
4. The parser never sees catalog data — matching bias is AGT-04's job, and keeping the parser catalog-blind preserves extraction ground truth.
5. Input text >6,000 chars for text path: chunk on blank lines with 200-char overlap, extract per chunk, merge via §5 (spans offset-adjusted).

## 8. Failure handling

| Event | Action |
|---|---|
| All pages fail vision | FAILED_PARSE, reason `VISION_ALL_PAGES_FAILED` |
| Model unavailable | FR-012 fallback model; if fallback also fails ×2 → FAILED_PARSE `MODEL_UNAVAILABLE` |
| xlsx unreadable/corrupt | FAILED_PARSE `XLSX_CORRUPT` |
| Text-layer probe wrong (digital pdf yields <2 lines) | auto-fallback to vision path once, flag `DIGITAL_FALLBACK_VISION` |

## 9. Observability

Spans per call: `chat qwen-vl-ocr` with `gen_ai.request.model`, page number attribute `qm.page`, tokens, duration. Trace summary: `"parsed 3 pages → 5 lines (1 QTY_MISSING) · buyer=Công ty TNHH Thành Công"`.

## 10. Evaluation criteria

| Metric | Target | Method |
|---|---|---|
| Line-item F1 (clean text) | ≥ 0.95 | EV-04, label match on (description_canon, qty) |
| Line-item F1 (scans) | ≥ 0.85 | EV-04 |
| Quantity exactness on xlsx | 100% | EV-04 |
| Diacritics byte-exact on labeled raw_text | 100% | EV-04 string compare |
| Never-invent check | 0 fabricated quantities on null-qty fixtures | 2 seeded fixtures |
| Latency | p50 ≤ 8 s text, ≤ 12 s/page vision | trace |

*End QM-AGT-03 v1.0.0.*
