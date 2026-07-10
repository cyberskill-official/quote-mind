# QuoteMind — Submission Description

**Document ID:** QM-SUB-DESC · **Version:** 1.0.0 · **Date:** 2026-07-10 · **Status:** Approved
**Parent spec:** QM-SPEC-001 v1.0.0 (SUB-05) · **Repo home:** `docs/submission-description.md`
**Usage:** paste the body below into the hackathon submission form's description field. Word count target ≤ 500 (body is ~490). Track declaration, repo URL, and video URL go in their own form fields; placeholders marked `{...}` must be filled on submission day.

---

## Submission form body

**Track 4 — Autopilot Agent · QuoteMind: an RFQ-to-quote autopilot for Vietnamese IT resellers**

Every quotation a Vietnamese IT reseller sends starts the same way: an RFQ arrives as a Vietnamese email, a scanned công văn PDF, or an English spreadsheet. A sales rep spends half a day parsing it, matching products, applying customer-tier pricing, computing 8% or 10% VAT, and formatting a bilingual báo giá, then chases a manager to check the math. QuoteMind automates that pipeline end to end while keeping the manager in command.

**How it works.** Eight specialized agents built on AgentScope 1.0 run on Alibaba Cloud Function Compute. An Orchestrator (qwen3-max with plan notebook) sequences the pipeline: intake classification (qwen-plus) detects language, urgency, and customer identity; the parser extracts line items from text (qwen-plus) or scanned pages (qwen-vl-ocr) with per-line confidence and byte-exact Vietnamese diacritics; the matcher resolves lines to catalog SKUs through hybrid retrieval on Tablestore, fusing vector search (text-embedding-v4, 1024-dim) with full-text search, and is code-forbidden from outputting any SKU outside its retrieved candidates.

**The design bet: AI never touches money.** Pricing, tier discounts, VAT, totals, and the Vietnamese amount-in-words are computed by a deterministic Decimal engine with 100% branch coverage. The drafter writes only the bilingual language around a read-only numeric skeleton, verified by checksum. Before any human sees a draft, a critic agent independently recomputes every figure from raw inputs and runs policy checks; its deterministic layer cannot be overridden by the LLM layer. In our fault-injection suite, the critic catches 10/10 seeded errors.

**Human-in-the-loop that survives serverless.** Quotes pause at `pending_approval` in a Tablestore state machine, so approval hours later starts a fresh Function Compute invocation that resumes exactly where the pipeline stopped. Managers approve, reject, or revise with plain-Vietnamese instructions ("accept the substitute, hold 8% margin"); below-floor margins require an audited waiver. Every step is recorded in a reasoning trace: agent, model, tools, tokens, and cost (under US$0.05 model cost for a typical text RFQ, trace-verified).

**Memory that learns and forgets.** Approved quotes become episodic memories per customer (tablestore-for-agent-memory). Retrieval scores similarity × importance × a 90-day half-life decay, so a returning customer's new quote cites real precedent ("như báo giá QM-2026-0007...") while stale memories are garbage-collected.

**Measured, not claimed.** On a 30-RFQ labeled evaluation set spanning clean text, scans, spreadsheets, and adversarial cases, the multi-agent pipeline achieves {X}% end-to-end success versus {Y}% for a single-agent baseline, with 100% price exactness and extraction F1 ≥ 0.95 on text / ≥ 0.85 on scans. Full eval harness and reports are in the repo.

**Stack.** DashScope (Singapore): qwen3-max, qwen-plus, qwen-vl-ocr, text-embedding-v4 · AgentScope 1.0 · Function Compute 3.0 · Tablestore (memory, state, vectors) · OSS · DirectMail · React dashboard. Deployment proof: `src/quotemind/infra/alibaba_proof.py` plus a verification script in the README. Apache-2.0, fully open source.

Built by CyberSkill (Ho Chi Minh City). Hiện Thực Hoá Ý Chí — Turn Your Will Into Real.

---

## Fill-in checklist for submission day

| Placeholder | Source |
|---|---|
| `{X}` pipeline success % | final EV-04 report, pipeline row |
| `{Y}` baseline success % | final EV-04 report, baseline row (FR-122) |
| Repo URL field | public GitHub URL after final push |
| Video URL field | YouTube link per QM-DEMO-001 §5 upload metadata |
| Track field | Track 4 — Autopilot Agent |

Rules honored: no unverifiable claims (every number traces to EV-01/04/05 artifacts); the two placeholder metrics must come from the same final eval run shown in the video (QM-DEMO-001 real-numbers rule); word count re-checked after filling placeholders (numbers do not change the count materially).

*End QM-SUB-DESC v1.0.0.*
