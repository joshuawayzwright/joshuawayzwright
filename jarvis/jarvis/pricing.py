"""Estimated Claude API cost from the token usage the API reports.

Prices are Anthropic's first-party API list prices in US dollars per million tokens (Claude API, November 2026).
Cache writes are priced at the 5-minute TTL, which is what Jarvis uses. These are estimates: they don't know
about discounts, partner-platform pricing (Bedrock, Vertex AI), fast mode, or Claude Haiku 5.5's higher rate for
prompts over 100K tokens, and when a safety-classifier fallback answers, the tokens are priced at Jarvis's own model.
"""

from __future__ import annotations

from collections.abc import Mapping

# model: (input, output, cache read, cache write) in USD per million tokens
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5-2": (8.00, 40.00, 0.20, 10.00),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}


def estimate_cost(model: str, usage: Mapping[str, int]) -> float | None:
    """Estimated cost in USD, or None for a model without a known price."""
    prices = PRICES.get(model)
    if prices is None:
        return None
    per_input, per_output, per_read, per_write = prices
    return (usage.get("input_tokens", 0) * per_input
            + usage.get("output_tokens", 0) * per_output
            + usage.get("cache_read_input_tokens", 0) * per_read
            + usage.get("cache_creation_input_tokens", 0) * per_write) / 1_000_000
