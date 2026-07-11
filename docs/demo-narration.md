# Demo clip: narration script (SUB-04)

The clip is **`.demo/quotemind-demo.mp4`** — 96 seconds, 1920×1080, no audio. Every frame is the
deployed product against live cloud data; nothing is a mockup.

Record your voice over it and mix. The captions are already burned in, so if a line lands late it
still reads. **Don't try to match the captions word for word** — say it your way. The timings below
are generous on purpose.

---

## 0:00–0:07 · Title

> Vietnamese IT resellers get RFQs as scanned purchase orders, spreadsheets, and half-Vietnamese
> emails. Turning one into a quote takes thirty to ninety minutes. Skilled work — and almost all of
> it mechanical.

## 0:07–0:15 · The idea

> So we built an autopilot for it. And it's built around one rule: **the model never does
> arithmetic.**
>
> Qwen does what it's excellent at — reading a messy Vietnamese email, working out that "20 con lap
> Dell i7" means twenty Latitude 5450s. Everything after that is ordinary, unit-tested Python.

## 0:15–0:23 · The queue

> Nothing is ever sent automatically. Every quote stops here, at a human gate. An autopilot that
> files a flight plan — and asks the captain before takeoff.

## 0:23–0:33 · One quote

> Here's a real one. Three Dell servers, four hundred and ninety-two million dong.
>
> The line is out of stock, so it carries its lead time. And the delivery terms were **retrieved**,
> not hardcoded — a made-to-order server never promises seven-day delivery, because that's a promise
> the business can't keep.

## 0:33–0:42 · The guarantee

> Every number on this page was computed in exact Decimal from the catalogue, and then
> **independently recomputed** by a critic. Recompute diffs: zero.
>
> A quote is a document a customer gets invoiced from. The model doesn't get to touch it.

## 0:42–0:50 · The gate

> Approve, reject, revise, cancel. And a flagged quote can't be approved silently — the waiver goes
> onto a hash-chained audit trail, with who signed it and why.

## 0:50–1:00 · The critic

> Look closely at this panel, because it's the whole architecture in one screen.
>
> The verdict is written by **code**, and it's labelled NOT AI. The note underneath is written by a
> model — **after** that verdict, from it — and it's labelled AI. It can explain the decision. It
> cannot change it.

## 1:00–1:09 · The trace

> The reviewer sees not just the price, but every step that produced it. Each model call, its
> tokens, its cost.

## 1:09–1:19 · The number

> And we measured whether any of this matters.
>
> Same models. Same catalogue. Same thirty labelled RFQs. Against a single agent asked to produce
> the whole quote: **ninety-three percent price-exact, against forty.**

## 1:19–1:28 · The grid

> One square per case. The single agent reads and matches almost as well — its SKU accuracy is
> within a point of ours.
>
> It gets the **money** wrong on sixty percent of quotes. And it never notices.

## 1:28–1:36 · Close

> Qwen on DashScope. AgentScope. Function Compute, Tablestore, OSS — deployed and live.
>
> A cent and a quarter a quote.

---

## Notes for the recording

- **Pace:** the clip is 96 s and the script is ~330 words. That's about 205 wpm — brisk but natural.
  If you run long, the two title cards (0:00 and 1:28) have the most slack.
- **The one line to land:** *"It gets the money wrong on sixty percent of quotes — and it never
  notices."* That's the whole argument. Pause before "and it never notices."
- **Don't oversell.** The numbers are real and they're strong. Read them flat; they do the work.
- If you re-record and want different beats, `.demo/` has every frame as a PNG and the compositor
  is `/tmp/qmvid/compose.py` — copy it into `deploy/` if you want it version-controlled.
