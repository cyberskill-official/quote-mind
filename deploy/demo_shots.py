"""Capture the live QuoteMind UI - element by element, so each beat is a tight, readable crop."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://quotemind.cyberskill.world"
OUT = Path("/tmp/qmvid/shots")
QID = "01KX9GKB10DGD1CRHERDR84CZN"
W, H = 1680, 1400


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)

        page.goto(f"{URL}/", wait_until="networkidle", timeout=90_000)
        page.wait_for_selector("li[data-id]", timeout=60_000)
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT / "01_queue.png")
        print("  01_queue")

        page.goto(f"{URL}/?quote={QID}", wait_until="networkidle", timeout=90_000)
        page.wait_for_selector(".cs-table", timeout=60_000)
        page.wait_for_timeout(2500)
        page.evaluate("document.querySelectorAll('details.section').forEach(d => d.open = true)")
        page.wait_for_timeout(800)

        # the quote itself: lines, the lead-time note, the totals
        page.locator(".pane").first.screenshot(path=OUT / "02_quote.png")
        print("  02_quote")

        # the guarantee
        page.locator(".deterministic").first.screenshot(path=OUT / "03_deterministic.png")
        print("  03_deterministic")

        # the human gate
        page.locator(".cs-review-gate").first.screenshot(path=OUT / "04_gate.png")
        print("  04_gate")

        # the critic: the code's verdict and the model's note, each labelled
        page.locator("details.section", has_text="Critic").first.screenshot(
            path=OUT / "05_critic.png"
        )
        print("  05_critic")

        # the reasoning trace
        trace = page.locator("details.section").last
        trace.screenshot(path=OUT / "06_trace.png")
        print("  06_trace")

        page.goto(f"{URL}/eval", wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(1500)
        page.locator("table").first.screenshot(path=OUT / "07_eval_table.png")
        print("  07_eval_table")
        page.locator(".grid").first.screenshot(path=OUT / "08_eval_grid.png")
        print("  08_eval_grid")

        browser.close()

    for shot in sorted(OUT.glob("*.png")):
        im_size = shot.stat().st_size
        print(f"  {shot.name:22} {im_size:>9,}")


if __name__ == "__main__":
    main()
