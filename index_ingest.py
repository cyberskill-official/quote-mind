"""Function Compute entry module for the OSS-drop ingest function (FR-021).

Same reasoning as index.py: FC controls sys.path, so src/ is put on it explicitly here rather than
through a PYTHONPATH we do not own.

`deploy/` is a scripts directory, not an importable package, so the ingest handler is loaded from
its file path. Adding an __init__.py purely to satisfy this import would turn a folder of
operational scripts into something that looks importable from anywhere - a worse lie than this is
a hack.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "src"))

_spec = importlib.util.spec_from_file_location(
    "qm_ingest", os.path.join(_ROOT, "deploy", "ingest.py")
)
assert _spec is not None and _spec.loader is not None
_ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ingest)


def handler(event: Any, context: Any = None) -> Any:
    """FC OSS-trigger entry point."""
    return _ingest.handler(event, context)


__all__ = ["handler"]
