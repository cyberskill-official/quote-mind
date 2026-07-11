# Demo script (SUB-04)

> **Rewritten 2026-07-12** after the live audit. The old script predated vision OCR, the OSS autopilot
> loop, episodic memory, the planner, and the deployed endpoint - it walked through a system that no
> longer exists. Shoot from this one.
>
> Everything below is verified live at
> https://quotemind-api-yccvwlooxw.ap-southeast-1.fcapp.run

Target: ~3 minutes, five beats. YouTube, public, "Not made for kids".

The whole video has one job: make the audience believe the numbers are right, and that a human is
still in command. Everything else is decoration. So the beat that matters most is beat 4 - the one
where the system refuses to do what it is told - and the script is paced to arrive there with time
to spare.

**Before recording:** `make seed` (61 SKUs, 8 customers), `make deploy`, `make deploy-frontend`,
`make proof` (confirm all Alibaba checks PASS). Have the dashboard open and the queue empty.

---

## Beat 1 - the problem (0:00-0:25)

*Screen: a real-looking Vietnamese RFQ email.*

> "This is what lands in a Vietnamese IT reseller's inbox. Three line items, mixed Vietnamese and
> English, no SKUs. Turning it into a quote takes a salesperson somewhere between thirty minutes and
> an hour: find the products, price them by customer tier, apply 8% VAT - 10% if it's telecom - and
> type it into a bilingual PDF."

Do not linger. The audience already believes this part.

## Beat 2 - the autopilot runs (0:25-1:10)

**The strongest single shot in the demo: drop a file, touch nothing, watch a quote appear.**

Drag `vi_scan_001.pdf` (a photographed, skewed purchase order) into `oss://quotemind-inbox/rfq/` -
in the OSS console, on camera. Say nothing for a beat. Then cut to the dashboard: a new quote is
already at the approval gate. Nobody clicked anything. No API call was made. A file landed in a
bucket and a priced, checked quote came out the other side.

Point at the plan panel: the scan was non-trivial, so it was planned, and every subtask closed with
a real outcome. Point at the trace: `qwen-vl-ocr` read the pages.

*Paste the RFQ into the dashboard. Hit submit. The quote appears in the queue.*

> "QuoteMind reads it, matches the catalog, works out this is a dealer, prices it, and drafts the
> quote. Twenty-three seconds, one cent."

*Open the quote. Show the bilingual line table, the VAT split, the amount in words.*

Say nothing clever here. Let it be boringly correct.

## Beat 3 - it remembers (1:10-1:35)

Open a quote for Thành Công. The **Prior decisions** panel shows what happened last time - which
quote, what the human decided, how long ago, ranked by `similarity x recency x importance`.

Say the line that matters: *"Memory informs the reviewer. It never touches the price."* A retrieved
document that could nudge a number would put a similarity search inside the arithmetic path, which
is the one thing this system is built never to do.

## Beat 4 - show the reasoning (1:35-2:05)

*Expand the reasoning-trace panel.*

> "And here is every step it took. The parse - qwen-plus, 1,262 tokens in. The catalog search - eight
> vector candidates, seven full-text. The SKU it picked, and how confident it was. Each step with its
> tokens, its cost, and how long it took.
>
> One thing is missing from this list: **at no point did the model do arithmetic.** It reads and it
> matches. The prices come from a deterministic engine with a hundred percent branch coverage, and a
> separate critic recomputes the whole quote and refuses to pass it if the numbers don't reconcile."

This is the technical heart of the submission. Do not rush it.

## Beat 4 - it refuses (1:50-2:30)

*Open the flagged quote - the one under the margin floor.*

> "This one it won't sign off. The blended margin is 4.8%, under the floor. It priced it, it drafted
> it - and then it stopped and asked."

*Click Approve. The waiver modal appears.*

> "I can override it. But I have to say so, and it goes on the record."

*Type the waiver. Approve. Show the audit trail with the waiver entry in it.*

> "Hash-chained. Who approved it, when, which flag they waived, and why."

**Then the sentence the whole video exists for:**

> "An autopilot that files a flight plan and asks the captain before takeoff."

## Beat 5 - the number (2:30-3:00)

*Screen: the eval table.*

> "We tested this against a single monolithic agent - same Qwen models, same catalog, same prompts -
> on twenty-five labelled RFQs.
>
> It reads just as well. It matches just as well. It gets **the money wrong on more than half the
> quotes** - and it never once notices.
>
> Taking arithmetic away from the model, and putting a critic behind it, is worth forty-eight points
> of end-to-end success. Eleven-tenths of a cent per quote."

*End card: repo URL, Track 4.*

---

## What not to do

- **Do not hide the failure.** If asked, the one case QuoteMind gets "wrong" is an RFQ for a laptop
  configuration that does not exist; it refuses to quote it and escalates. We think that is correct
  behaviour and the label is arguable. Saying so is more convincing than a suspicious 100%.
- **Do not fake the latency.** 23 seconds is a real number. Cutting to a pre-rendered quote and
  implying it was instant would be the one thing that, if noticed, discredits everything else.
- **Do not oversell the autonomy.** The gate is the feature. A judge who thinks this thing emails
  customers by itself will (correctly) distrust it.
