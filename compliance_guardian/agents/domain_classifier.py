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

import logging
import os
from typing import Dict, Iterable, Optional, List
import json

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


CLASSIFY_SYSTEM = "You assign compliance domains from {'scraping','finance','medical','other'}."

CLASSIFY_USER_TEMPLATE = """TEXT:
{prompt}

Return JSON only (one line):
{{"primary":"scraping|finance|medical|other","secondary":"scraping|finance|medical|other|null","confidence":0.0-1.0}}

If confidence < 0.6, set primary="other" and secondary=null.
"""


def _llm_classify(prompt: str, llm: Optional[str]) -> str:
    """Classify ``prompt`` with an LLM as a last resort."""

    LOGGER.info("Invoking LLM for domain classification")
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM},
        {"role": "user", "content": CLASSIFY_USER_TEMPLATE.format(prompt=prompt)},
    ]
    errors: List[str] = []
    if llm in {None, "openai"}:
        if openai is None:
            msg = "OpenAI package not installed"
            if llm == "openai":
                LOGGER.error(msg)
                raise RuntimeError(msg)
            errors.append(msg)
        elif not os.getenv("OPENAI_API_KEY"):
            msg = "OpenAI API key not configured"
            if llm == "openai":
                LOGGER.error(msg)
                raise RuntimeError(msg)
            errors.append(msg)
        else:
            try:
                client = openai.OpenAI()
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,  # type: ignore[arg-type]
                    temperature=0.1,
                    top_p=0.9,
                    max_tokens=200,
                )
                raw = resp.choices[0].message.content or "{}"
            except Exception as exc:  # pragma: no cover - LLM failure
                LOGGER.error("LLM classification failed: %s", exc)
                return "other"
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return "other"
            return data.get("primary", "other") or "other"
    if llm in {None, "gemini"}:
        if genai is None:
            msg = "Google Generative AI package not installed"
            if llm == "gemini":
                LOGGER.error(msg)
                raise RuntimeError(msg)
            errors.append(msg)
        elif not os.getenv("GEMINI_API_KEY"):
            msg = "Google Generative AI API key not configured"
            if llm == "gemini":
                LOGGER.error(msg)
                raise RuntimeError(msg)
            errors.append(msg)
        else:
            try:
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                model = genai.GenerativeModel("gemini-2.5-flash")
                res = model.generate_content(
                    "\n".join(m["content"] for m in messages),
                    generation_config={"temperature": 0.1, "top_p": 0.9},
                )
                raw = res.text or "{}"
            except Exception as exc:  # pragma: no cover - LLM failure
                LOGGER.error("LLM classification failed: %s", exc)
                return "other"
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return "other"
            return data.get("primary", "other") or "other"
    for err in errors:
        LOGGER.error(err)
    raise RuntimeError("No LLM credentials available")


# ---------------------------------------------------------------------------


def classify_domain(prompt: str, llm: Optional[str] = None) -> str:
    """Return the high-level domain for a user ``prompt``.

    The function first checks for obvious domain keywords. If no clear
    or multiple domains are matched it falls back to an LLM-based
    classifier. The resolved domain is logged and returned as a lower
    case string.
    """

    lowered = prompt.lower()
    hits = {
        name
        for name, words in _KEYWORDS.items()
        if any(w in lowered for w in words)
    }

    if len(hits) == 1:
        domain = hits.pop()
        LOGGER.info("Domain '%s' detected via keyword match", domain)
        return domain

    if not hits:
        LOGGER.info("No keyword match found; querying LLM")
    else:
        LOGGER.info("Ambiguous keywords %s; querying LLM", hits)

    if llm is not None:
        domain = _llm_classify(prompt, llm)
        LOGGER.info("LLM classified domain as '%s'", domain)
        return domain
    try:
        domain = _llm_classify(prompt, None)
        LOGGER.info("LLM classified domain as '%s'", domain)
        return domain
    except RuntimeError as exc:
        LOGGER.warning("LLM classification unavailable: %s; defaulting to 'other'", exc)
        return "other"


# ---------------------------------------------------------------------------


def _run_tests() -> None:
    """Simple unit tests exercised when run as a script."""
    assert classify_domain("Please scrape data from example.com") == "scraping"
    assert classify_domain("What stock should I buy today?") == "finance"
    assert classify_domain("Treatment options for flu symptoms") == "medical"
    print("domain_classifier tests passed")


if __name__ == "__main__":  # pragma: no cover
    _run_tests()
