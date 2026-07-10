# AGT-05 — PricingEngine — Agent Behavior Specification

**Document ID:** QM-AGT-05 · **Version:** 1.0.0 · **Parent:** QM-SPEC-001 v1.0.0 §6 (AGT-05), FR-050..056
**Implements in:** `src/quotemind/pricing/engine.py`, `vat.py`, `words_vi.py`; traced wrapper in `tools/pricing_tools.py`

---

## 1. Mission

Compute every monetary figure on a quote — unit prices, tier discounts, line totals, per-rate VAT, grand totals, margins, and the amount-in-words — with zero LLM involvement, full determinism, and 100% branch test coverage. This is the module the demo narrator points at when saying "the AI never touches your money".

## 2. Why this is specified as an "agent"

Judges and the dashboard see a uniform pipeline of agent steps. The PricingEngine is deterministic Python wrapped so it appears as `invoke_agent PricingEngine` in traces, with the same TraceStep schema. There is no ReActAgent, no model, no prompt file. The wrapper:

```python
async def price_quote(quote_id: str) -> ToolResponse:
    """Deterministic pricing of the matched quote. No LLM. FR-050..056."""
    with agent_span("PricingEngine"):
        matches, customer, extraction = load_inputs(quote_id)
        priced = engine.price(matches, customer, extraction, settings, today=date.today())
        persist(quote_id, priced)
        return summary_response(priced)   # ≤120-token summary for the Orchestrator
```

## 3. Input contract

- `list[MatchResult]` (DM-09) — only `matched` lines are priced; `needs_confirmation` lines are priced with their proposed sku (HITL may still change them); `no_match` lines pass through unpriced with quantity and description for HITL visibility.
- `CustomerProfile` (DM-06) — tier, project_discount_pct, preferred_currency.
- Full `CatalogProduct` per sku (including `cost_price_vnd`, visible only from here on).
- Config: `MARGIN_FLOOR_PCT`, `FX_USD_VND`, `QUOTE_VALIDITY_DAYS`, optional `VAT_DEFAULT_OVERRIDE`.
- Injected `today: date` (never wall-clock inside functions — NFR-002 determinism).

## 4. Computation rules (normative, FR-051..055)

1. **Unit price by tier:** end_customer → `list_price_vnd`; dealer → `dealer_price_vnd`; project → `dealer_price_vnd × (1 − project_discount_pct/100)`. Missing dealer_price → list_price + flag `DEALER_PRICE_MISSING`.
2. **Line total:** `qty × unit_price × (1 − discount_pct/100)`, `discount_pct` defaults 0 (populated on revise instructions only). All arithmetic in `Decimal`; VND amounts quantized `ROUND_HALF_UP` to 1 đồng at each line boundary.
3. **VAT:** per-line `vat_rate` from product (App. B mapping: IT categories 8%, telecom_service 10%); `vat_amount = line_total × rate/100` quantized per line; quote-level `vat_breakdown` groups by rate. Legal-basis footer string from `vat_policy_note(today)`.
4. **Totals:** `subtotal = Σ line_total`; `total = subtotal + Σ vat_amount`. Assertion: recomputing from lines reproduces totals exactly (self-check inside engine).
5. **Margin:** per line `(sell − cost×qty)/sell × 100` and blended; any line or blended < floor → `MARGIN_BELOW_FLOOR` (blocking).
6. **USD reference:** when customer prefers USD or language is en: `usd = vnd / FX_USD_VND`, ROUND_HALF_UP to cent, annotated "reference only, invoice in VND", rate + as-of date carried into the quote footer.
7. **Amount in words (words_vi.py):** grand total → formal Vietnamese, e.g. `1.234.000 → "Một triệu hai trăm ba mươi bốn nghìn đồng"`. Handles: mốt/tư/lăm variants, linh/lẻ, nghìn/triệu/tỷ groups, zero-group elision, và-insertion rules; ends with "đồng" (never "chẵn" in v1). Table-driven with the 30-case suite from FR-055.
8. **Number rendering:** VND `1.234.567 đ`; USD `$1,234.56`; dates `dd/mm/yyyy`.

## 5. Output contract — PricedQuote (feeds DM-10)

Per line: `sku?, qty, unit_price_vnd, discount_pct, line_total_vnd, vat_rate, vat_amount_vnd, margin_pct(internal), flags[]`. Quote level: `subtotal_vnd, vat_breakdown[{rate, base, amount}], total_vnd, total_in_words_vi, usd_reference?, blended_margin_pct(internal), flags[]`. Internal fields are stripped before any customer-facing artifact (render layer contract).

## 6. Guardrails

1. No imports of network, agents, or LLM clients — enforced by import-linter layer contract (repo blueprint §4).
2. No float anywhere in the money path: a unit test greps the AST of `pricing/` for `float(` and binary ops on floats.
3. Idempotence: same inputs → byte-identical serialized output (golden test).
4. Exceptions never yield partial totals: any error aborts to FAILED_PRICE (parent AGT-05 guardrail).
5. `words_vi` output must round-trip: a parser test converts words back to the number for the 30-case suite.

## 7. Failure handling

| Event | Action |
|---|---|
| Unknown sku at pricing time (race) | FAILED_PRICE `SKU_NOT_FOUND` |
| Negative or zero qty | line flagged `QTY_INVALID`, excluded from totals, non-blocking (HITL fixes) |
| vat_rate outside {0,5,8,10} | FAILED_PRICE `VAT_RATE_INVALID` (catalog data bug) |

## 8. Observability

Span `invoke_agent PricingEngine` with attributes `qm.lines_priced`, `qm.flags`, duration; no token attributes (no model). Trace summary: `"5 lines priced · subtotal 1.021.500.000 đ · VAT 8%: 81.720.000 đ · blended margin 9.4% · 1 flag"`.

## 9. Evaluation criteria

| Metric | Target | Method |
|---|---|---|
| Branch coverage of pricing/ | 100% | CI gate (NFR-010) |
| Property-based invariants (totals additive, quantization stable, tier monotonicity dealer ≤ list) | all hold | hypothesis suite EV-01 |
| bằng chữ suite | 30/30 | EV-01 |
| Price exactness across EV-04 | 100% | labels |
| Determinism golden | byte-identical | EV-01 |

*End QM-AGT-05 v1.0.0.*
