# QuoteMind

Autonomous RFQ-to-quote autopilot for Vietnamese IT reselling. CyberSkill's entry for the
Qwen Cloud Hackathon, Track 4 (Autopilot Agent).

![Track 4](https://img.shields.io/badge/Qwen%20Hackathon-Track%204%20Autopilot-45210E)
![License](https://img.shields.io/badge/license-Apache--2.0-F4BA17)
![Python](https://img.shields.io/badge/python-3.12-blue)

QuoteMind ingests an RFQ (Vietnamese or English text, PDF, scan, or Excel), extracts line
items, matches a seeded catalog, prices deterministically with 2026 Vietnamese VAT, drafts a
bilingual quote, and stops at a human approval gate before dispatch. The authoritative
specification lives in [`docs/spec/`](docs/spec/) (QM-SPEC-001); the repository blueprint is
QM-REPO-001.

## Quickstart

Requires Python 3.12.

```bash
cp .env.example .env      # fill in your keys (never commit .env)
make setup                # install the package + dev toolchain
make test                 # offline unit tests (no paid-API calls)
make dev                  # local API on http://localhost:9000  (GET /health)
```

`make setup` installs the light core plus the dev toolchain, which is all PR-1 needs.
The full runtime stack (agents, memory, cloud, parse, pdf, obs) is pinned in
`pyproject.toml` as extras and installed as later phases need it; `make setup-all` installs
everything.

## Proof of Alibaba Cloud Deployment

**[`src/quotemind/cloud/alibaba_proof.py`](src/quotemind/cloud/alibaba_proof.py)** — one runnable
file that exercises every Alibaba Cloud service QuoteMind depends on, against the real
`ap-southeast-1` region:

```bash
make proof          # python -m quotemind.cloud.alibaba_proof
```

| Service | What the proof does |
|---|---|
| **DashScope** (Model Studio, Singapore) | chat completion on `qwen3-max`; embedding on `text-embedding-v4`, asserting the 1024 dims the vector index requires |
| **OSS** | put → V4-presigned GET → HTTPS fetch → byte-compare → delete, on a Vietnamese payload |
| **Tablestore** | create table → put row → get row (diacritics byte-exact) → delete row |

Each check asserts on the *content* that came back, not merely on the absence of an exception — an
embedding check that only asserted "no error" would happily accept a wrong-width vector and corrupt
retrieval silently.

### It is deployed, and you can check it yourself

**https://quotemind-api-yccvwlooxw.ap-southeast-1.fcapp.run** — live on Function Compute 3.0 in
`ap-southeast-1` (Singapore).

> **⚠️ Read this before you click.** Function Compute injects `Content-Disposition: attachment` on
> every response from its default `*.fcapp.run` domain — it is a debugging endpoint, and Alibaba do
> not want it used to host pages. `curl` ignores that header; **a browser obeys it**, so the two HTML
> pages below *download* instead of rendering. This is a property of the endpoint, not of the app: a
> custom domain removes it in about fifteen minutes
> ([`docs/deploy/custom-domain.md`](docs/deploy/custom-domain.md)), and it is the next thing being
> done.
>
> **Everything below is verifiable with `curl` right now**, and that is the point of the table.

| Check | What it proves |
|---|---|
| `curl -s .../health` | version, the deployed git SHA, and the model ids actually in use — probed live from inside FC (FR-012) |
| `curl -s .../eval` | the 93%-vs-40% benchmark page, rendered from a committed snapshot (FR-104). Public, deliberately: a claim you cannot check is a claim you have to take on faith |
| `curl -s .../api/quotes` | `401` — every `/api/*` route requires `Authorization: Bearer $DEMO_API_TOKEN` (FR-010) |
| `curl -s .../` | the operator dashboard: approval queue, quote detail, the critic's verdict beside the model's note, reasoning trace, waiver modal (FR-100..106). Save it and open the file, or bind the domain |

To see the dashboard as a page today: `python deploy/demo_shots.py` renders it from the live API, and
[`.demo/quotemind-demo.mp4`](docs/demo-narration.md) is a 96-second walkthrough of it.

`/health` currently reports `"unverified": []` and `"substitutions": {}`. That is not a hardcoded
banner: on first need, the function probes every frozen model id from inside Function Compute
(FR-012), and those two empty lists mean each one answered and no documented fallback was needed. If
Alibaba retired `qwen-vl-ocr` tomorrow, `/health` would say so, name the substitute it switched to,
and keep serving.

Deployment descriptor: [`deploy/s.yaml`](deploy/s.yaml) — two functions, because they have genuinely
different shapes: `quotemind-api` on an HTTP trigger, and `quotemind-ingest` on an OSS
object-created trigger over `quotemind-inbox/rfq/`. They share one codebase and one pipeline; an
ingest path with its own copy of the quoting logic would be a second system that could disagree with
the first about the price.

The FC entry point is [`src/quotemind/api/fc.py`](src/quotemind/api/fc.py), and its docstring is
worth reading if you ever have to deploy FastAPI on Function Compute: FC 3.0 does *not* hand an HTTP
function a WSGI environ on the `fcapp.run` endpoint. It hands it an event envelope and expects one
back. Every wrong guess about that produces the same symptom — a 502 with no stack trace.

## The measured result

QuoteMind was evaluated against a **single monolithic agent** given the same Qwen models, the same
catalog and the same prompts, on **30 labelled RFQs** — five of them real scans:

| | task success | line F1 | SKU top-1 | price exact | flagged the problem | $/quote |
|---|---|---|---|---|---|---|
| **QuoteMind** | **93%** | 0.985 | 100% | **93%** | **10%** | $0.013 |
| single agent | 40% | 0.980 | 98% | 40% | **0%** | $0.011 |

The single agent reads and matches almost as well — its SKU accuracy is within two points of ours. It
gets **the money wrong on 60% of quotes**, and never once notices. Every one of its failures is
arithmetic.

That is the argument for the architecture: the model reads, deterministic code prices, and a critic
recomputes.

**The two points we lose are worth naming, because we chose not to buy them back.** One adversarial
case asks for a laptop configuration the catalog does not sell — 64GB RAM, 2TB SSD. The matcher is
shown the closest thing we *do* sell, a 32GB machine, and refuses to substitute it:

> *"None of the candidate SKUs meet the requested 64GB RAM and 2TB SSD specifications."*

The label expects the substitution. The system asks a human instead. We could have relabelled the
case and taken the point; quietly selling someone a 32GB laptop when they asked for 64GB is not a
rounding error, and a system whose entire premise is *stop rather than guess* should not be penalised
for stopping. It is now shown at the gate with the reason, the near-misses, and what the customer
actually asked for — a refusal is a decision, and the reviewer has to be able to act on it.

Reports: [`eval/reports/`](eval/reports/) · live at [`/eval`](docs/deploy/custom-domain.md) ·
reproduce with `make eval && make eval-snapshot`.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — the system, and the one idea it is built around
- [`docs/roadmap.html`](docs/roadmap.html) — live FR-by-FR progress
- [`docs/demo-script.md`](docs/demo-script.md) — the ~3-minute demo
- [`docs/submission-description.md`](docs/submission-description.md) — the submission text
- [`docs/spec/`](docs/spec/) — QM-SPEC-001, the authoritative specification

## License and tracking

Apache-2.0; see [`LICENSE`](LICENSE). Progress and decisions are in
[`BUILD_LOG.md`](BUILD_LOG.md); dependency pins in
[`docs/verification-log.md`](docs/verification-log.md); the FR-to-test map in
[`docs/traceability.csv`](docs/traceability.csv).
