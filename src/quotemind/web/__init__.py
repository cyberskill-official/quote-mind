"""TASK-106: the operator dashboard, shipped inside the package.

It lives here rather than in a top-level `web/` directory for one reason: it has to reach the
runtime. Function Compute bundles the code directory, the wheel bundles `src/`, and a sibling
directory is in neither by default - so a dashboard outside the package is a dashboard that only
exists on the developer's laptop.

The CyberSkill design system (github.com/cyberskill-official/design-system) is **vendored verbatim**
under `vendor/` and inlined here at serve time. Vendoring rather than importing is not laziness: the
dashboard is one self-contained page served by an event-driven Function Compute handler, with no
build step and no bundler to resolve `@cyberskill/tokens` for it.

Two things follow, and both matter more than the convenience:

  * The vendored files are **copies, never edits**. `vendor/MANIFEST.json` records the upstream
    commit and a sha256 of every file, and a test checks them. Hand-editing a vendored token to
    "just tweak the brand colour" is how a design system quietly dies, so it fails loudly instead.
  * The logo is the **master file's bytes**. DESIGN.md 1.2.x: the official mark "must be used -
    reproduced from the master file, never recreated, retraced, retyped, recoloured, rotated,
    stretched, or approximated." Redrawing it in CSS would have been quicker, and would have been
    wrong.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

_VENDOR = "quotemind.web.vendor"

# The order is load-bearing, and the design system says so:
#     tokens.css -> styles.css -> glass.css
# Glass is a render layer over the token anchors; a style pack (we ship none) would come last.
_CSS = ("cs-tokens.css", "cs-styles.css", "cs-glass.css")


def _vendored(name: str) -> str:
    return str((files(_VENDOR) / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def design_system_css() -> str:
    """The vendored CyberSkill design system, concatenated in its documented load order."""
    return "\n".join(_vendored(name) for name in _CSS)


@lru_cache(maxsize=1)
def logo_mark() -> str:
    """The official CyberSkill mark, byte-for-byte from the master file."""
    return _vendored("cs-logo-mark.svg")


@lru_cache(maxsize=1)
def manifest() -> dict[str, Any]:
    """What was vendored, from where, and at what hash."""
    loaded: dict[str, Any] = json.loads(_vendored("MANIFEST.json"))
    return loaded


def dashboard_html() -> str:
    """The dashboard source, design system inlined, API placeholders left for the caller."""
    page = str((files(__package__) / "index.html").read_text(encoding="utf-8"))
    return page.replace("/* __CS_DESIGN_SYSTEM__ */", design_system_css()).replace(
        "<!-- __CS_LOGO_MARK__ -->", logo_mark()
    )


__all__ = ["dashboard_html", "design_system_css", "logo_mark", "manifest"]
