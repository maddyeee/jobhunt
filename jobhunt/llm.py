"""Anthropic client wrapper. Sonnet 4.6 for bullet generation, Haiku 4.5
for cheap seniority classification."""
from __future__ import annotations
import os

from anthropic import Anthropic

SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"

_client: Anthropic | None = None


def client() -> Anthropic:
    global _client
    if _client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        _client = Anthropic(api_key=key)
    return _client
