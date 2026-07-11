"""Build the QuoteMind demo clip: real screenshots, burned-in captions, no voice.

Stephen records the voiceover on top, so the captions carry the beats and the timing is generous
enough to read them aloud. Everything on screen is the deployed product against live cloud data.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHOTS = Path("/tmp/qmvid/shots")
FRAMES = Path("/tmp/qmvid/frames")
FONTS = Path("/Users/stephencheng/Projects/CyberSkill/quote-mind/src/quotemind/quote/render/fonts")
OUT = Path("/Users/stephencheng/Projects/CyberSkill/quote-mind/.demo/quotemind-demo.mp4")

W, H = 1920, 1080
UMBER = (69, 33, 14)
OCHRE = (244, 186, 23)
CREAM = (253, 250, 245)
INK = (28, 20, 13)
MUTED = (150, 128, 108)

BAR = 250  # caption bar height


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"BeVietnamPro-{weight}.ttf"), size)


F_KICKER = font("Bold", 26)
F_HEAD = font("Bold", 48)
F_BODY = font("Regular", 30)
F_TITLE = font("Bold", 92)
F_SUB = font("Regular", 40)
F_MONO = font("SemiBold", 32)


def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=f) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def card(kicker: str, head: str, body: str) -> Image.Image:
    """A full-bleed title card, for the beats that are an argument rather than a screen."""
    im = Image.new("RGB", (W, H), UMBER)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 14, H], fill=OCHRE)

    y = 300
    d.text((150, y), kicker.upper(), font=F_KICKER, fill=OCHRE)
    y += 70
    for line in wrap(d, head, F_TITLE, W - 340):
        d.text((150, y), line, font=F_TITLE, fill=CREAM)
        y += 108
    y += 30
    for line in wrap(d, body, F_SUB, W - 380):
        d.text((150, y), line, font=F_SUB, fill=(214, 196, 178))
        y += 58
    return im


def shot(
    name: str, kicker: str, head: str, body: str, crop: tuple[int, int, int, int] | None = None
) -> Image.Image:
    """A screenshot of the live product, with a caption bar under it."""
    im = Image.new("RGB", (W, H), UMBER)
    d = ImageDraw.Draw(im)

    # Every proof frame names where it was taken. The clip used to be shot against a local
    # uvicorn, which proved nothing a judge could check; these are the live site.
    kicker = f"{kicker}  \u00b7  quotemind.cyberskill.world"

    src = Image.open(SHOTS / name).convert("RGB")
    if crop:
        src = src.crop(crop)

    area_h = H - BAR
    scale = min(W / src.width, area_h / src.height)
    src = src.resize((int(src.width * scale), int(src.height * scale)), Image.LANCZOS)
    im.paste(src, ((W - src.width) // 2, (area_h - src.height) // 2))

    # caption bar
    d.rectangle([0, H - BAR, W, H], fill=UMBER)
    d.rectangle([0, H - BAR, W, H - BAR + 5], fill=OCHRE)

    y = H - BAR + 34
    d.text((100, y), kicker.upper(), font=F_KICKER, fill=OCHRE)
    y += 46
    d.text((100, y), head, font=F_HEAD, fill=CREAM)
    y += 66
    for line in wrap(d, body, F_BODY, W - 200)[:2]:
        d.text((100, y), line, font=F_BODY, fill=(206, 186, 166))
        y += 40
    return im


# (image, seconds). The durations are set so a narrator can read the beat comfortably.
BEATS: list[tuple[Image.Image, float]] = [
    (
        card(
            "Qwen Cloud Hackathon · Track 4",
            "QuoteMind",
            "An RFQ-to-quote autopilot for Vietnamese IT resellers. A scanned purchase order, a "
            "spreadsheet, half-Vietnamese email — 30 to 90 minutes of skilled, mechanical work.",
        ),
        7.0,
    ),
    (
        card(
            "the idea it is built around",
            "The model never does arithmetic.",
            "Qwen reads the messy Vietnamese and picks the SKU. Every number after that is "
            "ordinary, unit-tested Python — and a critic recomputes the whole quote from source.",
        ),
        8.0,
    ),
    (
        shot(
            "01_queue.png",
            "the review queue",
            "Nothing is ever sent automatically.",
            "Every quote stops at the human gate. An autopilot that files a flight plan and asks "
            "the captain before takeoff.",
        ),
        8.0,
    ),
    (
        shot(
            "02_quote.png",
            "one RFQ, read and priced",
            "Three Dell servers. 492,480,000 ₫.",
            "The line is out of stock, so it carries its lead time. The delivery terms were "
            "retrieved from procedural memory — a made-to-order server never promises 7 days.",
        ),
        10.0,
    ),
    (
        shot(
            "03_deterministic.png",
            "the guarantee, on the page",
            "No model touched these numbers.",
            "Computed in exact Decimal from the catalogue, then independently recomputed by the "
            "critic. Recompute diffs: zero.",
        ),
        9.0,
    ),
    (
        shot(
            "04_gate.png",
            "the human gate",
            "Approve. Reject. Revise. Cancel.",
            "A flagged quote cannot be approved silently - the waiver goes onto a hash-chained "
            "audit trail, with who signed it and why.",
        ),
        8.0,
    ),
    (
        shot(
            "05_critic.png",
            "the critic",
            "One verdict. Two authors. Both labelled.",
            "NOT AI: the deterministic check. AI: a note written after that verdict, from it — and "
            "structurally unable to change it.",
        ),
        10.0,
    ),
    (
        shot(
            "06_trace.png",
            "show your work",
            "Every model call, its tokens, its cost.",
            "The reviewer sees not just the price but every step that produced it. A flagged quote "
            "cannot be approved silently: the waiver is hash-chained onto the audit trail.",
        ),
        9.0,
    ),
    (
        shot(
            "07_eval_table.png",
            "we measured it",
            "93% price-exact. The single agent: 40%.",
            "Same models, same catalogue, same 30 labelled RFQs. The only difference is the "
            "architecture.",
        ),
        10.0,
    ),
    (
        shot(
            "08_eval_grid.png",
            "one square per case",
            "17 of 30 we get right and it does not.",
            "The single agent reads and matches almost as well. It gets the money wrong on 60% of "
            "quotes — and never notices.",
        ),
        9.0,
    ),
    (
        card(
            "deployed on Alibaba Cloud",
            "$0.013 a quote.",
            "Qwen on DashScope · AgentScope · Function Compute · Tablestore for state and agent "
            "memory · OSS. Live, and every number on it is measured.",
        ),
        8.0,
    ),
]


def main() -> None:
    FRAMES.mkdir(parents=True, exist_ok=True)
    for old in FRAMES.glob("*.png"):
        old.unlink()

    listing = []
    for i, (im, secs) in enumerate(BEATS):
        path = FRAMES / f"beat_{i:02d}.png"
        im.save(path)
        listing.append((path, secs))
        print(f"  beat {i}: {secs:>4.1f}s")

    concat = FRAMES / "concat.txt"
    lines = []
    for path, secs in listing:
        lines.append(f"file '{path}'")
        lines.append(f"duration {secs}")
    lines.append(f"file '{listing[-1][0]}'")  # ffmpeg needs the last frame repeated
    concat.write_text("\n".join(lines))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-vf",
        "fps=30,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "20",
        "-movflags",
        "+faststart",
        str(OUT),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    total = sum(s for _, s in listing)
    print(f"\n  {OUT}  ({OUT.stat().st_size / 1_000_000:.1f} MB, {total:.0f}s)")


if __name__ == "__main__":
    main()
