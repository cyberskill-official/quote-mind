"""FR-104: freeze the newest eval run into the snapshot the deployed /eval page renders.

    make eval-snapshot

The page does not run the eval. It renders this file. That is a deliberate constraint rather than a
shortcut: a page that recomputed its own numbers on every load could quietly disagree with the
number in the submission, and nobody would ever know which one was true. Committing the snapshot
means the headline claim moves only when a human commits a new one.
"""

from __future__ import annotations

import glob
import json
import os
import sys

from quotemind.eval_.report import SNAPSHOT, snapshot


def _newest(pattern: str) -> str:
    matches = sorted(glob.glob(pattern), key=os.path.getmtime)
    if not matches:
        sys.exit(f"no eval report matches {pattern} - run `make eval` first")
    return matches[-1]


def main() -> None:
    pipeline_path = _newest("eval/reports/*_pipeline.json")
    baseline_path = _newest("eval/reports/*_baseline.json")

    with open(pipeline_path, encoding="utf-8") as handle:
        pipeline = json.load(handle)
    with open(baseline_path, encoding="utf-8") as handle:
        baseline = json.load(handle)

    data = snapshot(pipeline, baseline)
    SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    won = sum(
        1
        for case in data["cases"]
        if case["pipeline_price_exact"] and not case["baseline_price_exact"]
    )
    print(f"snapshot: {os.path.basename(pipeline_path)} + {os.path.basename(baseline_path)}")
    print(f"  pipeline price-exact: {data['pipeline']['price_exactness']:.0%}")
    print(f"  baseline price-exact: {data['baseline']['price_exactness']:.0%}")
    print(f"  cases we price exactly and the single agent does not: {won}/{len(data['cases'])}")
    print(f"  written to {SNAPSHOT}")


if __name__ == "__main__":
    main()
