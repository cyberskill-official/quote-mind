"""Function Compute entry module (TASK-003).

FC imports the handler relative to the code root, and its Python runtime controls `sys.path` itself
- it prepends `/code` and `/code/python` and does not reliably honour a `PYTHONPATH` we set in the
function's environment. This project keeps its package under `src/`, so relying on `PYTHONPATH` to
make `quotemind` importable is a bet on runtime behaviour we do not control, and when it loses, the
function fails at *import* time: a 502 in 200 ms with no request ever reaching the app.

So `src/` is put on the path here, explicitly, in the one file FC is guaranteed to import. The
handler is then `index.handler` - no environment variable in the loop.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from quotemind.api.fc import handler, initialize  # noqa: E402  (must follow the sys.path insert)

__all__ = ["handler", "initialize"]
