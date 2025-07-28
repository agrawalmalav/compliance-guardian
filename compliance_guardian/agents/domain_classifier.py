"""Domain classifier for the Compliance Guardian agents.

This module provides a simple keyword-based domain classifier with
an optional LLM-based fallback when keywords are insufficient for
resolution. Supported domains are ``scraping``, ``finance``, ``medical``
and ``other``. The function logs which detection path was used and the
final classification result.
"""

from __future__ import annotations

# Version of this agent module. Including explicit versions in logs
# ensures audit trails can be recreated with the exact implementation
# used when a decision was made.
__version__ = "0.2.1"

import json
import logging
import os
from typing import Dict, Iterable

try:
    import openai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    openai = None  # type: ignore

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    genai = None  # type: ignore


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Simple keyword mapping for heuristic classification
_KEYWORDS: Dict[str, Iterable[str]] = {
    "scraping": ["scrape", "crawler", "harvest", "spider"],
    "finance": ["stock", "investment", "trade", "bank", "finance"],
    "medical": ["diagnosis", "treatment", "symptom", "patient", "disease"],
}


# ---------------------------------------------------------------------------


def _llm_classify(prompt: str) -> str:
    """Classify ``prompt`` with an LLM as a last resort."""
    system = (
        "Classify this user prompt as one of: 'scraping', 'finance', "
        "'medical', or 'other': {prompt}"
    ).format(prompt=prompt)

    LOGGER.info("Invoking LLM for domain classification")
    try:
        if openai and os.getenv("OPENAI_API_KEY"):
            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": system}],
                temperature=0,
            )
            raw = resp.choices[0].message.content or ""
            text = raw.strip().lower()
        elif genai and os.getenv("GEMINI_API_KEY"):
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel("gemini-pro")
            res = model.generate_content(system)
            text = res.text.strip().lower()
        else:  # pragma: no cover - only hits when no API keys configured
            LOGGER.warning("No LLM credentials available; defaulting to 'other'")
            return "other"
    except Exception as exc:  # pragma: no cover - LLM failure
        LOGGER.error("LLM classification failed: %s", exc)
        return "other"

    for dom in ("scraping", "finance", "medical"):
        if dom in text:
            return dom
    return "other"


# ---------------------------------------------------------------------------


def classify_domain(prompt: str) -> str:
    """Return the high-level domain for a user ``prompt``.

    The function first checks for obvious domain keywords. If no clear
    or multiple domains are matched it falls back to an LLM-based
    classifier. The resolved domain is logged and returned as a lower
    case string.
    """

    lowered = prompt.lower()
    hits = {
        name for name, words in _KEYWORDS.items() if any(w in lowered for w in words)
    }

    if len(hits) == 1:
        domain = hits.pop()
        LOGGER.info("Domain '%s' detected via keyword match", domain)
        return domain

    if not hits:
        LOGGER.info("No keyword match found; querying LLM")
    else:
        LOGGER.info("Ambiguous keywords %s; querying LLM", hits)

    domain = _llm_classify(prompt)
    LOGGER.info("LLM classified domain as '%s'", domain)
    return domain


# ---------------------------------------------------------------------------


def _run_tests() -> None:
    """Simple unit tests exercised when run as a script."""
    assert classify_domain("Please scrape data from example.com") == "scraping"
    assert classify_domain("What stock should I buy today?") == "finance"
    assert classify_domain("Treatment options for flu symptoms") == "medical"
    print("domain_classifier tests passed")


if __name__ == "__main__":  # pragma: no cover
    _run_tests()
