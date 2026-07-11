"""FR-106: the operator dashboard, shipped inside the package.

It lives here rather than in a top-level `web/` directory for one reason: it has to reach the
runtime. Function Compute bundles the code directory, the wheel bundles `src/`, and a sibling
directory is in neither by default - so a dashboard outside the package is a dashboard that only
exists on the developer's laptop.
"""

from __future__ import annotations

from importlib.resources import files


def dashboard_html() -> str:
    """The dashboard source, placeholders unsubstituted."""
    return (files(__package__) / "index.html").read_text(encoding="utf-8")


__all__ = ["dashboard_html"]
