"""Function Compute entry points (FR-003).

FC 3.0 runs an ASGI app directly when the handler is a callable, so this is a thin shim rather than
a translation layer: `handler` *is* the FastAPI app. Anything more clever here - a hand-rolled
event-to-request adapter, say - would be a second HTTP implementation that could drift from the one
every test exercises, and the first anyone would hear of it is a 500 in production.

`initialize` is the FC initializer: it runs once per cold start, before any request is served, and
performs the FR-012 model-availability probe.
"""

from __future__ import annotations

from typing import Any

from ..obs.log import configure_logging
from .app import app
from .app import initialize as _initialize

# FC collects stdout, so JSON lines to stdout is the whole logging story (FR-008).
configure_logging()

handler = app


def initialize(context: Any = None) -> None:
    """FC initializer. Probes the frozen model ids and activates any documented fallback."""
    _initialize(context)


__all__ = ["handler", "initialize"]
