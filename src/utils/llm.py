"""Pluggable LLM provider abstraction.

One interface, three backends selected by the ``LLM_PROVIDER`` env var:

* ``mock``      — deterministic, zero-cost, no network. Default; lets the repo
                  clone-and-run and keeps evals hermetic.
* ``openrouter``— routes to Claude (default) or any OpenRouter model. Uses
                  ``OPENROUTER_API_KEY``. Honors the "default to Claude" rule.
* ``gemini``    — Google GenAI, uses ``GOOGLE_API_KEY`` (GCP credits).

Nodes depend only on :class:`LLMProvider`, never on a concrete SDK — the
provider-agnostic seam is intentional and swappable in one line.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

# Default Claude model when routing through OpenRouter (per project convention).
DEFAULT_CLAUDE_MODEL = "anthropic/claude-opus-4.1"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class LLMProvider(ABC):
    """Minimal chat interface every backend implements."""

    @abstractmethod
    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """Return a single completion string.

        Args:
            system: System prompt.
            user: User message.
            json_mode: Hint that the caller expects a JSON object back.

        Returns:
            The model's text response.
        """
        raise NotImplementedError


class MockProvider(LLMProvider):
    """Deterministic stand-in used for offline runs and hermetic evals.

    Intent classification is keyword-driven so tests are stable; narration
    echoes a compact deterministic summary. This is intentionally dumb — the
    graph's *control flow* and deterministic resolution are what we test, not
    the mock's prose.
    """

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        text = user.lower()
        if json_mode:
            return json.dumps({"intent": self._classify(text)})
        return "OK"

    @staticmethod
    def _classify(text: str) -> str:
        rules = [
            (("suicide", "kill myself", "self harm", "self-harm", "hurt myself",
              "end my life"), "escalation"),
            (("agent", "representative", "human", "supervisor", "person",
              "useless", "ridiculous"), "escalation"),
            (("refill", "reorder", "renew"), "refill"),
            (("price", "cost", "how much", "copay"), "drug_price"),
            (("cancel", "update address", "change address", "expedite",
              "payment method", "approve"), "order_action"),
            (("thank", "goodbye", "bye", "all set", "that's all", "done"), "closing"),
            (("order", "prescription", "rx", "status", "where is", "shipped",
              "delivery", "arrive", "medication", "meds"), "order_status"),
        ]
        for needles, intent in rules:
            if any(n in text for n in needles):
                return intent
        return "off_topic"


class OpenRouterProvider(LLMProvider):
    """OpenRouter backend (reaches Claude, GPT, Gemini via one API)."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_CLAUDE_MODEL)
        self.api_key = os.environ["OPENROUTER_API_KEY"]

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        import httpx  # local import keeps mock path dependency-free

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class GeminiProvider(LLMProvider):
    """Google GenAI backend (uses GCP credits)."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_GEMINI_MODEL)
        self.api_key = os.environ["GOOGLE_API_KEY"]

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        gen_config: dict[str, Any] = {"temperature": 0}
        if json_mode:
            gen_config["responseMimeType"] = "application/json"
        resp = httpx.post(
            url,
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": gen_config,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def get_provider() -> LLMProvider:
    """Instantiate the provider named by ``LLM_PROVIDER`` (default ``mock``).

    Returns:
        A ready-to-use :class:`LLMProvider`.

    Raises:
        ValueError: If ``LLM_PROVIDER`` names an unknown backend.
    """
    name = os.getenv("LLM_PROVIDER", "mock").lower()
    if name == "mock":
        return MockProvider()
    if name == "openrouter":
        return OpenRouterProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {name!r} (expected mock|openrouter|gemini)")
