# QuoteMind — Track 4: Autopilot Agent

**Submission description (SUB-05).** 455 words of prose (532 by `wc -w` if you count the headings,
the table and the URL). The previous version claimed 491 and was actually 506 - and it quoted eval
numbers from a 25-case run that no longer exists. Both are fixed.
**Live:** https://quotemind.cyberskill.world

---

A Vietnamese IT reseller's day starts with a pile of RFQs: a scanned purchase order, a spreadsheet,
an email in half-Vietnamese half-English. Turning one into a quote takes 30-90 minutes - reading it,
hunting SKUs, pricing by tier, applying 2026's 8% VAT (10% for telecom), typing a bilingual PDF.
Skilled work, almost all of it mechanical.

**QuoteMind is an autopilot for that job.** An RFQ arrives - pasted, uploaded, or dropped into an OSS
bucket - and the system runs the whole path: read it (OCR if it is a scan), match the catalog,
resolve the tier, price it, self-check, render the PDF. Then it stops, and asks a human.

## The idea it is built around

A quote is a document a customer gets invoiced from. So: **the model is never allowed to do
arithmetic.**

Qwen does what it is excellent at - reading a messy Vietnamese email, working out that "20 con lap
Dell i7 32GB" means twenty Latitude 5450 i7 laptops, and picking that SKU from a catalog of
near-identical variants. Everything after that is ordinary, unit-tested Python: `Decimal` prices, VAT
bands, totals, amount-in-words. A critic then recomputes the whole quote from source data and refuses
to pass one whose numbers do not reconcile.

**We measured whether that matters.** Against a single monolithic agent given the same models, the
same catalog and the same 30 labelled RFQs, five of them real scans:

| | task success | **price exact** | flagged the problem |
|---|---|---|---|
| QuoteMind | **93%** | **93%** | 10% |
| single agent | 40% | **40%** | **0%** |

The single agent reads and matches almost as well - its SKU accuracy is within two points of ours. It
gets the **money wrong on 60% of quotes, and never notices.** That is a system that mails a customer
a wrong price with total confidence. Taking arithmetic away from the model, and putting a critic
behind it, is worth **+53 points**.

The two points we lose are worth naming, because we chose not to buy them back. One adversarial case
asks for a laptop configuration the catalog does not sell - 64GB RAM, 2TB SSD. The matcher is shown
the closest thing we do sell, a 32GB machine, and refuses to substitute it. The label expects the
substitution; the system asks a human instead. We could have relabelled the case. Quietly selling
someone a 32GB laptop when they asked for 64GB is not a rounding error, and a system that stops
rather than guesses should not be penalised for stopping.

## It remembers, and it plans

On every human decision QuoteMind writes an episodic memory: what was quoted, and what the human
decided, in their words. Before quoting a known customer it recalls the top three, ranked by
`similarity x recency x importance` - so last week's rejection outranks last year's approval. Memory
informs the reviewer; it never touches a price. Non-trivial quotes are decomposed in AgentScope's
PlanNotebook, and the plan reports what actually ran - including the steps handed to a human.

## What it runs on

Qwen (`qwen3-max`, `qwen-plus`, `qwen-vl-ocr`, `text-embedding-v4`) on DashScope Singapore;
AgentScope; Function Compute 3.0 (HTTP API + OSS-triggered ingest); Tablestore for durable state and
agent memory; OSS for inputs, PDFs and traces.

## The gate is the feature

Nothing is sent automatically. Every quote stops at `pending_approval`, and the reviewer sees not
just the price but **every step that produced it** - each model call, its tokens, its cost. A flagged
quote cannot be approved silently: the waiver goes onto the hash-chained audit trail, with who signed
it and why.

An autopilot that files a flight plan and asks the captain before takeoff. **$0.013 a quote.**
