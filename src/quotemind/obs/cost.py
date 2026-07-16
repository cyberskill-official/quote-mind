"""Cost accounting (TASK-112).

Token counts times a checked-in price table. Money again, so again Decimal: a float would drift and
the eval report would be quietly wrong. Unknown models cost nothing rather than crashing a quote -
but they are reported, so a missing price is visible instead of silently zero forever.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

PRICES_FILE = "model_prices.yaml"
_PER_TOKENS = Decimal(1_000_000)
_CENTS = Decimal("0.000001")  # report to the microdollar; per-call costs are tiny


class ModelPrices:
    """The parsed price table."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.as_of: str = str(raw.get("as_of", "unknown"))
        self.currency: str = str(raw.get("currency", "USD"))
        self.endpoint: str = str(raw.get("endpoint", "unknown"))
        self._models: dict[str, dict[str, Decimal]] = {
            name: {
                "input": Decimal(str(entry.get("input", 0))),
                "output": Decimal(str(entry.get("output", 0))),
            }
            for name, entry in (raw.get("models") or {}).items()
        }

    @property
    def models(self) -> list[str]:
        return sorted(self._models)

    def known(self, model: str) -> bool:
        return model in self._models

    def cost_usd(self, model: str, tokens_in: int, tokens_out: int = 0) -> Decimal:
        """USD for one call. An unpriced model returns 0 (and `known()` says why)."""
        entry = self._models.get(model)
        if entry is None:
            return Decimal(0)
        total = (
            entry["input"] * Decimal(tokens_in) + entry["output"] * Decimal(tokens_out)
        ) / _PER_TOKENS
        return total.quantize(_CENTS)


@lru_cache(maxsize=1)
def load_prices() -> ModelPrices:
    """The checked-in price table shipped with the package."""
    text = resources.files("quotemind.config").joinpath(PRICES_FILE).read_text(encoding="utf-8")
    return ModelPrices(yaml.safe_load(text))


def cost_usd(model: str, tokens_in: int, tokens_out: int = 0) -> Decimal:
    """Convenience wrapper over the loaded table."""
    return load_prices().cost_usd(model, tokens_in, tokens_out)
