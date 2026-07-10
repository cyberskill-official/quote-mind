# QuoteMind — Demo Video Script & Shot List

**Document ID:** QM-DEMO-001 · **Version:** 1.0.0 · **Date:** 2026-07-10 · **Status:** Approved
**Parent spec:** QM-SPEC-001 v1.0.0 (SUB-04, §2.4 demo beats UJ-01..05) · **Repo home:** `docs/demo-script.md`
**Target:** one public video, 3:00 ± 10 s, YouTube (unlisted or public), marked "Not made for kids", 1080p minimum, English narration with Vietnamese UI content visible on screen.

---

## 1. Strategy for this video

Judges score Presentation & Documentation at 15%, but a strong demo also carries the other 85%: it is the only place most judges will see Technical Depth, Innovation, and Problem Value in motion. The structure below follows the pattern that wins comparable hackathons: problem stated in the first 20 seconds, what-before-how, a controlled live run with the reasoning trace visible, before/after numbers, and the architecture on screen while the pipeline runs. Everything demoed is real: no mockups, no sped-up fakery beyond honest time-lapse cuts labeled as such.

Three rules for the presenter:
1. Never say "AI magic". Name the mechanism ("the critic recomputes every total from raw inputs").
2. Every claim on screen has a number or an artifact behind it.
3. The HITL pause is the emotional center of the video: slow down there, speed up everywhere else.

## 2. Pre-production checklist

- [ ] EV-08 rehearsal completed on the deployed stack; all five beats timed and stable.
- [ ] Seed state reset: `make seed` fresh; customer `cust_thanhcong` has the QM-2026-0007 episodic history (UJ-04 depends on it).
- [ ] Two RFQ fixtures staged: `vi_text_003.txt` (UJ-01) and `vi_scan_002.pdf` (UJ-02 quick cut; generated scan fixture per Appendix A.5).
- [ ] UJ-03 fixture staged: the out-of-catalog + below-margin request.
- [ ] Dashboard zoom level 110%, browser chrome hidden (F11), demo bearer token pre-entered.
- [ ] Trace panel pre-tested: expands without scroll jank; token/cost columns visible.
- [ ] Eval report page shows the latest full run (pipeline vs baseline side-by-side).
- [ ] `architecture.png` exported at 2200 px for the cutaway; sequence PNG as backup.
- [ ] Screen recorder at 1080p60; system notifications off; VN keyboard input tested for the revise instruction.
- [ ] Microphone check; quiet room; narration script printed.
- [ ] Timer overlay OFF (we cite wall-clock verbally; on-screen clock in the dashboard header is enough).

## 3. Shot-by-shot script

Column key: TC = target timecode start; V = visual; N = narration (spoken, English); OSD = on-screen text overlay (bilingual where noted).

### Beat 0 — Cold open: the problem (0:00–0:20)

| TC | V | N | OSD |
|---|---|---|---|
| 0:00 | Static title card 2 s: QuoteMind logo (Umber/Ochre), subtitle "RFQ-to-Quote Autopilot · Qwen Cloud Hackathon Track 4" | — | "Track 4: Autopilot Agent" |
| 0:02 | Split screen: left, a real-looking Vietnamese RFQ email; right, a sales rep's cluttered spreadsheet + Word quote in progress | "A Vietnamese IT reseller gets requests like this all day: Vietnamese emails, scanned công văn PDFs, English spreadsheets. Answering one takes a rep half a day: catalog lookup, discounts, VAT, a bilingual quote, then chasing a manager to check it." | "1 RFQ ≈ nửa ngày công / half a day of work" |
| 0:14 | Cut to dashboard queue, empty state | "QuoteMind collapses that to minutes, and keeps the manager in command. Watch one request go end to end." | "Live on Alibaba Cloud · ap-southeast-1" |

### Beat 1 — UJ-01 happy path, Vietnamese text RFQ (0:20–1:05)

| TC | V | N | OSD |
|---|---|---|---|
| 0:20 | Paste `vi_text_003.txt` into the RFQ intake box; click submit; 202 toast with quote_id | "A Vietnamese email: twenty Dell Latitude laptops, twenty monitors, twenty-five Microsoft 365 seats. Submitted." | "POST /api/rfq → 202" |
| 0:27 | Queue row appears; status chips animate received → parsing → matching → pricing → drafting → validating (honest time-lapse label if cut) | "Eight agents take over: classify language and customer, extract line items with confidence, then match against the catalog by vector similarity plus full-text, fused." | "AgentScope 1.0 · qwen-plus · text-embedding-v4 (1024)" |
| 0:44 | Status hits pending_approval; open quote detail: bilingual line table, confidence chips, totals with VAT 8% line | "Ninety seconds later: a bilingual draft. And here is the part that matters for production: every price, every VAT amount, every total came from deterministic code. The language model never does arithmetic on your money." | "Thuế GTGT 8% · NĐ 174/2025/NĐ-CP" + green badge "Deterministic pricing" |
| 0:56 | Expand the reasoning trace panel; scroll slowly through agent steps with token counts and cost | "Every step is on the record: which agent, which Qwen model, which tools, how many tokens, what it cost. This quote: about four cents." | "Full reasoning trace · $0.04" |

### Beat 2 — UJ-02 scanned công văn, quick cut (1:05–1:25)

| TC | V | N | OSD |
|---|---|---|---|
| 1:05 | Drag `vi_scan_002.pdf` into the OSS inbox (console or upload UI); ingest trigger fires; jump-cut (labeled) to the parsed line table with the scan page thumbnail beside it | "Scanned documents too: a stamped công văn PDF hits the bucket, the OSS trigger fires, and qwen-vl-ocr reads the table off the page image, diacritics intact." | "OSS trigger → qwen-vl-ocr · F1 ≥ 0.85 on scans" |
| 1:20 | Side-by-side: scan region vs extracted line with matching highlight | — | — |

### Beat 3 — UJ-03 ambiguity + HITL: the centerpiece (1:25–2:10)

| TC | V | N | OSD |
|---|---|---|---|
| 1:25 | Open the third quote, already at pending_approval with two flag badges | "Now the case that decides whether you can trust an autopilot. This request asks for a drawing tablet we do not carry, and pushes for project pricing below our margin floor." | Flags visible: "NEEDS_CONFIRMATION" · "MARGIN_BELOW_FLOOR" |
| 1:34 | Hover the flagged line: substitution note in Vietnamese and English naming requested vs offered item; then the critic's bilingual note | "The matcher refuses to fake a match: it proposes the nearest real product and says exactly what differs, in both languages. The critic independently recomputed every total and flagged the margin at 4.2 percent, below our 5 percent floor. Nothing ships past this screen without a human." | "Critic recomputes 100% of totals" |
| 1:48 | Type the revise instruction in Vietnamese: "Đồng ý thay thế, giữ margin 8%, thêm ghi chú giao hàng 2 tuần." Click Revise | "The manager answers in plain Vietnamese: accept the substitute, hold eight percent margin, add a two-week delivery note." | "Human-in-the-loop · revise with instructions" |
| 1:57 | Status revising → drafting → validating → pending_approval; open v2: margin now green, new delivery note present; click Approve | "The drafter obeys, pricing recomputes deterministically, the critic re-checks, and version two comes back clean. Approve." | "revision 2 · blended margin 8.0% ✓" |
| 2:05 | Toast: approved → dispatching → sent | "And the pause survives serverless: approval started a fresh invocation resumed from Tablestore state." | "Durable HITL across invocations" |

### Beat 4 — Dispatch + memory (2:10–2:30)

| TC | V | N | OSD |
|---|---|---|---|
| 2:10 | Open the generated PDF: header band, bilingual table, VAT breakdown, bằng chữ line, bank block; scroll once | "The deliverable: a professional bilingual báo giá, rendered to PDF, stored on OSS, emailed with a time-limited link." | "WeasyPrint · Be Vietnam Pro · OSS presigned URL" |
| 2:18 | Back to the first customer; open the UJ-04 quote; highlight the drafter's line "như báo giá QM-2026-0007..." and the memory citation chip in the trace | "And it remembers. A returning customer's new request references their March quote and the substitution they accepted, retrieved by importance-weighted memory that also forgets: stale, low-value memories decay and get garbage-collected." | "Episodic memory · similarity × decay × importance" |

### Beat 5 — Architecture + numbers + close (2:30–3:00)

| TC | V | N | OSD |
|---|---|---|---|
| 2:30 | Full-screen `architecture.png`, camera pans left to right: Qwen Cloud models → agent pipeline → Tablestore/OSS → dashboard | "All native Alibaba Cloud: Qwen 3 Max, Plus, VL-OCR and embeddings through DashScope; AgentScope agents on Function Compute; Tablestore for memory, state and vector search; OSS and DirectMail out the back." | Callout arrows on the four zones |
| 2:42 | Eval report page: side-by-side table pipeline vs single-agent baseline; zoom the success-rate delta row | "We measured it. On a thirty-RFQ labeled set, the multi-agent pipeline beats a single-agent baseline by double digits on end-to-end success, with one hundred percent price correctness, because the money path is code, not completion." | "Pipeline vs baseline: +N pts success · 100% price exactness" (insert real numbers from the final EV-04 run) |
| 2:52 | Title card: repo URL, "Apache-2.0", track badge, CyberSkill mark | "QuoteMind. Track 4, Autopilot Agent. Repo, docs, and the full spec are open source. Turn your will into real." | Repo URL · "Proof of deployment in README" |

Hard stop at 3:00–3:10.

## 4. Narration timing budget

Full narration above is ~430 words. At a measured 145 wpm that is just under 3:00 of speech across 3:00 of video: tight but correct, because beats 1 and 3 contain natural pauses while the UI works. If rehearsal runs long, cut in this order: (1) the second sentence of Beat 2, (2) the "durable HITL" aside at 2:05 (keep the OSD), (3) shorten Beat 0's second sentence. Never cut the deterministic-pricing line, the critic recompute line, or the baseline numbers.

## 5. Production notes

- **Honesty labels.** Any time-compressed segment gets a small "time-lapse" OSD. Judges forgive waiting; they do not forgive fakery.
- **Real numbers rule.** The +N delta and $0.04 cost are placeholders: pull the final EV-04 report values the day of recording; the script reader must not invent them.
- **Language.** Narration in English (international judges); every on-screen document is bilingual, which silently demonstrates the differentiator the whole time.
- **Cursor discipline.** Move-pause-click; no circling. Zoom (Ctrl+scroll) only on the trace and the flags.
- **Audio.** Voice only, no music bed (music fights the 3-minute pace and adds licensing risk). Normalize to -16 LUFS.
- **Accessibility.** Upload an .srt of the narration; YouTube auto-captions Vietnamese OSD poorly, so the srt is the record.
- **Thumbnail.** Dashboard quote-detail screenshot with the two flag badges visible + title "RFQ → Approved Quote in Minutes".
- **Upload metadata.** Title: "QuoteMind — Autopilot RFQ-to-Quote Agent on Qwen Cloud (Track 4)". Description: first line = one-sentence pitch, then repo link, architecture link, track declaration, timestamped chapters matching the five beats. Visibility public or unlisted; "Not made for kids"; no shorts remix.

## 6. Contingency cuts (if a live segment breaks on recording day)

| Segment | Fallback |
|---|---|
| Beat 2 scan parse | Use the EV-08 rehearsal screen recording of the same fixture (labeled "recorded earlier") |
| Beat 3 revise round-trip latency spike | Cut the waiting, keep request + result, label time-lapse |
| Eval page not ready | Show `eval/reports/summary.md` rendered in the repo instead |
| DirectMail hiccup | Stub transport is the demo default anyway; show the .eml artifact in OSS and say "stub transport for the demo; SMTP path is one env var" |

## 7. Mapping to judging criteria (why each beat exists)

| Beat | Primarily proves |
|---|---|
| 0 | Problem Value: authentic pain, quantified |
| 1 | Technical Depth: multi-model routing, hybrid retrieval, deterministic money; Presentation: trace |
| 2 | Technical Depth: qwen-vl-ocr multimodal; Innovation: one pipeline for all inputs |
| 3 | Track-4 core: ambiguity handling + HITL; Innovation: critic recompute; Technical Depth: durable serverless state |
| 4 | Innovation: memory with decay inside a business agent; Problem Value: real deliverable |
| 5 | Technical Depth: native stack; Innovation: measured multi-agent gain; Presentation: architecture + numbers |

*End QM-DEMO-001 v1.0.0.*
