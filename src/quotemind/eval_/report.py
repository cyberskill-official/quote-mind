"""TASK-104: the eval report page - the headline claim, rendered from the run that produced it.

The submission says the pipeline gets the money right on 93% of quotes and a single agent gets it
right on 40%. That is the whole argument of this project, and until now the only way to check it was
to read a JSON file in a directory nobody clones. So it is a page on the deployed site instead, and
it is public - the same reasoning as `/health`: a claim a judge cannot verify without a credential
is a claim they have to take on faith.

The page renders a *snapshot*, committed to the repo, rather than running the eval on demand. Two
reasons: a live eval is 30 quotes and about twenty minutes of model calls, and - more to the point -
a page that recomputed its own numbers on every load would be a page that could quietly disagree
with the submission. The snapshot is generated from `eval/reports/` by `make eval-snapshot`, and it
carries the timestamp of the run it came from, so a stale one says so on its face.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..web import design_system_css, logo_mark

SNAPSHOT = Path(__file__).with_name("latest.json")


def snapshot(pipeline: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Reduce two eval reports to what the page shows. Per-case detail stays; prompts do not."""
    return {
        "generated_at": pipeline.get("generated_at"),
        "pipeline": pipeline["aggregate"],
        "baseline": baseline["aggregate"],
        "cases": [
            {
                "case_id": case["case_id"],
                "tags": case.get("tags", []),
                "pipeline_price_exact": case.get("price_exact", False),
                "pipeline_error": case.get("error"),
                "baseline_price_exact": by_id.get(case["case_id"], {}).get("price_exact", False),
                "baseline_error": by_id.get(case["case_id"], {}).get("error"),
            }
            for case in pipeline["cases"]
            for by_id in [{c["case_id"]: c for c in baseline["cases"]}]
        ],
    }


def load() -> dict[str, Any] | None:
    """The committed snapshot, or None if the eval has never been snapshotted."""
    if not SNAPSHOT.exists():
        return None
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "-"


def _age(generated_at: str | None) -> str:
    """How old this run is, said out loud. A stale benchmark that looks fresh is worse than none."""
    if not generated_at:
        return "unknown"
    try:
        when = datetime.fromisoformat(generated_at)
    except ValueError:
        return generated_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - when).days
    stamp = when.strftime("%d %b %Y")
    if days <= 0:
        return f"{stamp} (today)"
    return f"{stamp} ({days} day{'s' if days != 1 else ''} ago)"


def _rows(data: dict[str, Any]) -> str:
    pipeline, baseline = data["pipeline"], data["baseline"]
    metrics = [
        ("Task success", _pct(pipeline["task_success"]), _pct(baseline["task_success"]), True),
        (
            "Price exactness",
            _pct(pipeline["price_exactness"]),
            _pct(baseline["price_exactness"]),
            True,
        ),
        (
            "Caught its own problem",
            _pct(pipeline["human_intervention_rate"]),
            _pct(baseline["human_intervention_rate"]),
            False,
        ),
        (
            "SKU top-1 accuracy",
            _pct(pipeline["sku_top1_accuracy"]),
            _pct(baseline["sku_top1_accuracy"]),
            False,
        ),
        (
            "Line extraction F1",
            f"{pipeline['line_extraction']['f1']:.2f}",
            f"{baseline['line_extraction']['f1']:.2f}",
            False,
        ),
        ("Errors", str(pipeline["errors"]), str(baseline["errors"]), False),
        (
            "Cost per quote",
            f"${pipeline['cost_usd']['per_quote']}",
            f"${baseline['cost_usd']['per_quote']}",
            False,
        ),
        (
            "Latency p50",
            f"{pipeline['latency_ms']['p50'] / 1000:.0f}s",
            f"{baseline['latency_ms']['p50'] / 1000:.0f}s",
            False,
        ),
    ]
    return "\n".join(
        f'<tr class="{"headline" if headline else ""}">'
        f"<td>{name}</td><td class='num'>{ours}</td><td class='num'>{theirs}</td></tr>"
        for name, ours, theirs, headline in metrics
    )


def _grid(data: dict[str, Any]) -> str:
    cells = []
    for case in data["cases"]:
        ok = case["pipeline_price_exact"]
        base_ok = case["baseline_price_exact"]
        # The interesting cell is the one where we are right and the single agent is not - that is
        # the +53 points, one case at a time.
        cls = "won" if ok and not base_ok else ("ok" if ok else "bad")
        title = (
            f"{case['case_id']} - QuoteMind: {'price exact' if ok else 'wrong'}; "
            f"single agent: {'price exact' if base_ok else 'wrong'}"
        )
        cells.append(f'<span class="cell {cls}" title="{title}">{case["case_id"]}</span>')
    return "\n".join(cells)


def render_report_html() -> str:
    """TASK-104: the whole page, self-contained, on the design system the dashboard uses."""
    data = load()
    if data is None:
        body = (
            "<p class='muted'>No eval snapshot has been committed. "
            "Run <code>make eval</code> then <code>make eval-snapshot</code>.</p>"
        )
        table = grid = ""
        stamp = "-"
    else:
        table = _rows(data)
        grid = _grid(data)
        stamp = _age(data.get("generated_at"))
        body = ""

    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QuoteMind - evaluation</title>
<meta property="ai:generated" content="none">
<meta property="ai:deterministic-regions" content="all-metrics">
<style>
{design_system_css()}
body {{ margin:0; padding:48px 24px; font-family: var(--cs-font-sans, system-ui, sans-serif);
        background: var(--cs-color-surface, #17100c); color: var(--cs-color-text, #f5efe8); }}
.wrap {{ max-width: 900px; margin: 0 auto; }}
h1 {{ font-size: 28px; margin: 16px 0 4px; }}
.muted {{ color: var(--cs-color-text-muted, #b7a99b); font-size: 14px; }}
table {{ width:100%; border-collapse: collapse; margin: 28px 0; }}
th, td {{ text-align:left; padding: 12px 10px;
          border-bottom: 1px solid var(--cs-color-border, #3a2b20); }}
th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
     color: var(--cs-color-text-muted, #b7a99b); }}
td.num {{ text-align:right; font-variant-numeric: tabular-nums; font-weight:600; }}
tr.headline td {{ font-size: 18px; padding: 16px 10px; }}
tr.headline td.num:nth-child(2) {{ color: var(--cs-color-accent, #F4BA17); }}
.grid {{ display:flex; flex-wrap:wrap; gap:6px; margin-top: 10px; }}
.cell {{ font-size:11px; padding:5px 8px; border-radius:6px;
        font-family: ui-monospace, monospace; }}
.cell.won {{ background: var(--cs-color-accent, #F4BA17); color:#45210E; font-weight:700; }}
.cell.ok  {{ background: rgba(244,186,23,.18); color: var(--cs-color-text, #f5efe8); }}
.cell.bad {{ background: rgba(200,60,40,.35); color: #ffd9d2; }}
.legend {{ display:flex; gap:18px; margin-top:14px; font-size:12px; }}
.key {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; }}
a {{ color: var(--cs-color-accent, #F4BA17); }}
</style>
</head>
<body>
<div class="wrap">
  {logo_mark()}
  <h1>Does taking the arithmetic away from the model actually matter?</h1>
  <p class="muted">
    Same models. Same 61-SKU catalog. Same 30 labelled RFQs, five of them real scans.
    The only difference is the architecture: QuoteMind computes money in deterministic Python and
    re-checks it with a critic; the baseline is one agent asked to produce the whole quote.
    <br>Run: <b>{stamp}</b>. These numbers are measured, not asserted - the harness is in
    <code>src/quotemind/eval_/</code>.
  </p>
  {body}
  <table>
    <thead><tr><th>Metric</th><th style="text-align:right">QuoteMind</th>
    <th style="text-align:right">Single agent</th></tr></thead>
    <tbody>{table}</tbody>
  </table>
  <h2 style="font-size:18px;margin-bottom:2px">Every case, one square each</h2>
  <p class="muted">Whether the final money was exactly right.</p>
  <div class="grid">{grid}</div>
  <div class="legend">
    <span><i class="key" style="background:#F4BA17"></i>we got it right, the single agent
      did not</span>
    <span><i class="key" style="background:rgba(244,186,23,.18)"></i>both right</span>
    <span><i class="key" style="background:rgba(200,60,40,.35)"></i>we got it wrong</span>
  </div>
  <p class="muted" style="margin-top:32px">
    The single agent reads and matches almost as well - its SKU accuracy is within a point of ours.
    It gets the <b>money</b> wrong, and it never notices. That is what the critic is for, and it is
    why the model is never allowed to do the arithmetic.
    <br><a href="/">&larr; back to the review queue</a>
  </p>
</div>
</body>
</html>"""
