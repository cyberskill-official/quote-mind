# Known limitations

Everything below is a thing we know is imperfect and chose to leave. A limitation you have written
down is a decision; one you have not is a bug you have not met yet. Each entry says what the
behaviour is, why it is that way, and what it would cost to change.

## TASK-134 — an in-flight quote cannot be cancelled

`POST /api/quotes/{id}/cancel` works at the approval gate. On a quote that is still **running** it
returns `409 illegal_transition`, with a message that says exactly why.

Two things make it so, and only one of them is ours:

1. **Function Compute cannot interrupt a background task.** The pipeline runs to completion. Even a
   perfect API-level cancel would not stop the model calls that are already in flight.
2. **The status enum is frozen.** QM-SPEC-001 §12 lists the statuses in the DO-NOT-CHANGE registry,
   and there is no `cancelled` among them. Cancellation is therefore recorded as the transition to
   `rejected`, distinguished by its audit event — `human.cancel`, never `human.rejected`. The
   dashboard reads the event, not the status, so a reviewer sees "cancelled", not "rejected".

Making an in-flight cancel *work* means widening `LEGAL_TRANSITIONS`, which §12 says to stop and ask
about — and it would still not stop the run. It would need a cancellation check before every write,
or the finished pipeline would happily write its result onto a quote the human had already
abandoned. That is a race, added late, to buy an edge case; the 409 is a correct answer to a question
the platform genuinely cannot answer differently.

**What a reviewer actually loses:** a few seconds. Wait for the gate, then cancel.

## TASK-133 — structured output is not used on the vision path

`structured_model=` is wired at the text parser, the matcher and the eval baseline: the model is
handed a schema and the SDK guarantees the shape. The vision path parses `qwen-vl-ocr`'s JSON by
hand, because **`qwen-vl-ocr` is an OCR model, not a tool-calling one** — it has no structured-output
mode to use. This is not an unfinished corner; it is the model's capability boundary, and the frozen
registry (§12) names that model.

The hand-parse is defensive, and the critic recomputes every number that comes out of it regardless,
so a malformed OCR response produces a flagged quote, not a wrong one.

## TASK-036 — one document is one quote

The spec allows splitting a single document containing several unrelated RFQs into several quotes.
We do not. P2, and out of scope for the demo: an RFQ that is really two RFQs is a document-triage
problem, and solving it badly (splitting when you should not have) produces two wrong quotes instead
of one right question.

## TASK-074 — there is no auto-fix loop, deliberately

The spec allows the critic to hand a failing quote back to the drafter to repair itself. We route
every defect to a human instead.

This is the one non-goal worth arguing for rather than apologising for. **An autopilot that quietly
repairs its own defects is the exact thing this product exists to argue against.** The measured
result is that the single-agent baseline gets the money wrong on 60% of quotes and never notices; a
self-repair loop is that same confidence, wearing a seatbelt. When the critic and the drafter
disagree about a price, the interesting information is *that they disagree*, and it belongs in front
of the person whose name goes on the invoice.

## TASK-091 — the PDF route hands back a signed URL, it does not redirect

The spec allows a 302 to the object. We return the URL in JSON instead, and the docstring on
`quote_pdf` explains why at length. The short version: the route is bearer-guarded, and a 302 is only
useful to a client that can *follow a link* — a plain `<a href>` carries no `Authorization` header.
The custom domain lifted Function Compute's cross-domain redirect ban, so the redirect is now
*possible*; it was never the better shape. TASK-091's actual guarantee — the object stays private,
reachable only through a short-lived signed URL — is preserved either way, and preserved more usably
by handing the URL back.

## The two eval points we did not buy back

QuoteMind scores 93%, not 95%, because one adversarial case asks for a laptop the catalog does not
sell (64GB RAM, 2TB SSD) and the matcher **refuses to substitute** the 32GB machine we do sell. The
label expects the substitution. We could move the label. Quietly selling someone a 32GB laptop when
they asked for 64GB is not a rounding error, and a system whose whole premise is *stop rather than
guess* should not be penalised for stopping. The refusal is shown at the gate with the near-misses
and the reason, so a human can decide in seconds.

## The frozen model id is not a frozen model

§12 freezes `qwen3-max`. It cannot freeze its weights. Our headline moved from 97% to 93% between two
runs of an unchanged eval on unchanged code, because the model behind the id changed underneath us.
This is inherent to building on a hosted model and worth stating plainly rather than quoting the
best number we ever saw. The **baseline moved too** — it is measured in the same run, against the
same models, which is the entire point of measuring it at all. The gap is the claim, and the gap held.

## The public dashboard carries the demo credential, deliberately

View the source of `/` and you will find `DEMO_API_TOKEN` in the page. This is not an oversight —
the docstring on the route (`api/app.py::dashboard`) says it out loud. A public demo page must carry
a credential to be usable at all: the alternative is a login screen in front of judges, guarding
seeded demo data. It is bounded three ways: every write path still stops at the human approval gate,
nothing dispatches without a person clicking approve; the token is a single rotatable value (it has
already been rotated once); and the data behind it is the seeded catalog and demo quotes, not
customer data. A production tenant puts this behind the identity provider the spec's section 3.2
calls for — that is a deployment decision, not an architecture change.

## Artifacts are private, and stay private

OSS **Block Public Access** is an account-level setting on this account. The artifacts bucket holds
customer quote PDFs, so this is a feature, not an obstacle: nothing in the bucket is reachable
without a signed URL, and we did not turn it off to make a demo easier.

## The custom domain is the deployment, not a nicety

`*.fcapp.run` sends `Content-Disposition: attachment` on every response. If the custom domain lapses,
the dashboard becomes a download again. `deploy/smoke.py` asserts the header's absence on every run,
so this fails loudly rather than silently. The certificate is Let's Encrypt (90 days); renewal is
`python deploy/issue_cert.py` and needs no redeploy, because the ACME challenge is served from OSS.
