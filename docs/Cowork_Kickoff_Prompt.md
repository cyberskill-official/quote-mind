# Cowork kickoff prompt — QuoteMind build

Paste the block below as the first message in a new Claude Cowork session, with QuoteMind_Spec_Pack_v1.0.zip attached or unzipped into the session workspace.

---

You are implementing QuoteMind, an RFQ-to-quote autopilot for Vietnamese IT resellers, submission for the Qwen Cloud Hackathon Track 4 (Autopilot Agent). The attached spec pack QuoteMind_Spec_Pack_v1.0.zip is the complete and authoritative specification. Unzip it and treat it as read-only input.

Pack contents and their roles:
- QuoteMind_PRD_SRS_v1.0.md (QM-SPEC-001 v1.0.0): master spec. 85 functional requirements in epics EP-01..13, data models DM-01..14, APIs API-01..13, NFRs, eval plan EV-01..08, seed data in Appendix A, PDF layout in Appendix C, frozen repo tree in Appendix D, 14-day schedule in Appendix F. Section 1 contains reading instructions written for you; follow them.
- QuoteMind_Repo_Blueprint_v1.0.md (QM-REPO-001): normative repo tree, module-contract import layering (enforced by import-linter), Makefile targets, CI jobs, and the bootstrap order PR-1..PR-5. Build in exactly that PR order.
- agent-specs/ (QM-AGT-01..08 + INDEX.md): per-agent construction code, versioned system prompts, tool contracts, code-enforced guardrails, failure routing, and eval targets. Load only the one sheet relevant to the feature you are implementing, per INDEX.md.
- QuoteMind_Architecture_v1.0.md + architecture.png + pipeline-sequence.png: C4 views and the submission diagram (SUB-03). architecture.mmd and pipeline-sequence.mmd are the editable sources; regenerate PNGs only via the diagrams Make target if they change.
- QuoteMind_Demo_Script_v1.0.md (QM-DEMO-001): the 3:00 video plan. Not code, but EV-08 rehearsal and the seed state it needs (customer cust_thanhcong with QM-2026-0007 history, fixtures vi_text_003.txt and vi_scan_002.pdf) are build requirements.
- QuoteMind_Submission_Description_v1.0.md (QM-SUB-DESC): final form text. Two placeholders {X} and {Y} must be filled from the final EV-04 run; never invent them.

Hard rules, non-negotiable:
1. The DO-NOT-CHANGE registry in QM-SPEC-001 section 12 is frozen: model constants (qwen3-max, qwen-plus, qwen-vl-ocr, text-embedding-v4 at dimensions=1024), env var names, table names (qm_quotes, qm_audit, qm_counters), bucket names (quotemind-inbox, quotemind-artifacts), API routes, quote numbering QM-YYYY-NNNN, status enums, and the trace schema. If you believe a frozen item must change, stop and ask; do not improvise.
2. Money is deterministic: pricing, VAT, totals, and amount-in-words are pure Decimal Python (pricing/ imports no network, agents, or LLM clients). The LLM never does arithmetic. The critic's Layer-1 recompute is authoritative and the LLM layer cannot override it.
3. Guardrails are code-enforced (set-membership checks, checksums, middleware call caps), never prompt-only. Implement them exactly as the agent sheets specify.
4. Stack is fixed: AgentScope 1.0.x (not agentscope-runtime), tablestore-for-agent-memory==1.1.3, DashScope international (Singapore) endpoint, Function Compute 3.0 python3.12 in ap-southeast-1, OSS, DirectMail with stub fallback, WeasyPrint==68 with bundled Be Vietnam Pro, Apache-2.0 license.
5. Every PR maps to task ids via branch naming (feat/TASK-042-catalog-matcher) and updates traceability.csv, per the repo blueprint.
6. Bilingual integrity: Vietnamese diacritics byte-exact everywhere; every customer-facing text field is BilingualText with both vi and en populated.

Working method:
- Start with PR-1 (scaffold) from the repo blueprint section on bootstrap order, and proceed PR-1 through PR-5, then continue epic by epic following Appendix F's 14-day schedule.
- For each feature: read the task text in QM-SPEC-001, the relevant agent sheet if it touches an agent, and the module contract in QM-REPO-001. Write tests to the acceptance criteria stated in the task before or alongside the implementation.
- Verification snippets in QM-SPEC-001 Appendix E must be run early (PR-4 memory-verify, PR-5 proof + deploy) because several SDK signatures were flagged as needing wheel verification; if a real API differs from the spec's assumption, report the difference and adapt the thin wrapper layer only, keeping contracts intact.
- Maintain a running BUILD_LOG.md: date, PR, tasks covered, deviations (if any) with justification, and open questions.
- Ask before deviating; small ambiguities you may resolve yourself if you log them.

Definition of done for the hackathon: all P0 tasks implemented and tested, EV-01..05 green with EV-04 report generated (fills {X}/{Y}), deployed to Alibaba Cloud with alibaba_proof.py output in the README, seed and demo Make targets working so the demo script's five beats run on the deployed stack, repo public under Apache-2.0.

Begin by unzipping the pack, reading QM-SPEC-001 sections 1-4 and the repo blueprint in full, then present your PR-1 plan.

---

Notes for the operator (not part of the prompt):
- If Cowork's session has the pack pre-unzipped, replace the first sentence accordingly.
- Feed additional context lazily: the pack is designed for per-feature loading, so resist pasting whole documents into chat; point Cowork at file paths instead.
- The two research reports from the planning phase are intentionally excluded; the spec pack supersedes them.
