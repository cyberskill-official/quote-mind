# QuoteMind - Track 4: Autopilot Agent

**Submission description (SUB-05).** 491 words (limit 500).

---

A Vietnamese IT reseller's day starts with a pile of RFQs: a Zalo message, a scanned purchase order,
a spreadsheet, an email in half-Vietnamese half-English. Turning each one into a quote takes a
salesperson 30-90 minutes - reading it, hunting the SKUs, pricing by customer tier, applying 2026's
8% VAT (10% for telecom), and typing it all into a bilingual PDF. It is skilled work, and almost all of it is mechanical.

**QuoteMind is an autopilot for that job.** An RFQ arrives - pasted, uploaded, or dropped into an OSS
bucket - and it runs the whole path itself: parse, match the catalog, resolve the customer's tier,
price, draft, self-check, and render a bilingual quote PDF. Then it stops, and asks a human.

## The idea the system is built around

A quote is a document a customer gets invoiced from. So: **the language model is never allowed to do
arithmetic.**

Qwen does what it is genuinely excellent at - reading a messy Vietnamese email and working out that
"20 con lap Dell i7 32GB" means twenty Latitude 5450 i7 laptops, then picking that SKU from a catalog
of near-identical variants. Everything after that is ordinary, unit-tested Python: `Decimal` prices,
VAT bands, totals, amount-in-words. A critic then recomputes the whole quote from source data and
refuses to pass one whose numbers do not reconcile.

**We measured whether this matters.** Against a single monolithic agent given the same models, the
same catalog and the same prompts, on 25 labelled RFQs:

| | task success | line F1 | SKU top-1 | price exact | flagged the problem |
|---|---|---|---|---|---|
| QuoteMind | **96%** | 0.992 | 100% | **96%** | - |
| single agent | **48%** | 0.992 | 98% | **48%** | **0%** |

The single agent reads and matches almost as well. It gets the **money wrong on 52% of quotes** - and
never once notices. That is a system that mails a customer a wrong price with total confidence.
Taking arithmetic away from the model and putting a critic behind it is worth **+48 points**.

## What it runs on

Qwen (`qwen3-max`, `qwen-plus`, `qwen-vl-ocr`, `text-embedding-v4`) via DashScope Singapore;
AgentScope for orchestration; Function Compute 3.0 for the API and the OSS-triggered ingest;
Tablestore as both durable state (hash-chained audit trail, atomic quote numbering) and agent memory
(vector + full-text retrieval fused by RRF); OSS for inputs, PDFs and reasoning traces; DirectMail
for dispatch.

## The gate is the feature

Nothing is ever sent automatically. Every quote stops at `pending_approval`, durably, and a reviewer
sees not just the price but **every step that produced it** - each model call, tool call and memory
lookup, with its tokens, cost and duration. A quote the critic flagged cannot be approved silently:
the waiver is written into the audit chain, with who signed it and why.

An autopilot that files a flight plan and asks the captain before takeoff. Cost: **$0.011 per quote.**
