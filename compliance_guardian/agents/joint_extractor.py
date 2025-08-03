"""Joint domain and instruction extractor.

This module performs domain classification and explicit user rule
extraction in a *single* call. When no LLM credentials are available a
heuristic fallback is used. The function returns detected domains and a
list of temporary ``Rule`` objects representing user or session specific
instructions.
"""

from __future__ import annotations

__version__ = "0.1.0"

import json
import logging
import os
import re
from typing import List, Tuple, Optional


from compliance_guardian.utils.models import (
    Rule,
    RuleType,
    SeverityLevel,
    ComplianceDomain,
)
from compliance_guardian.utils.text import _strip_code_fence

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

_KEYWORDS = {
    "scraping": ["scrape", "crawler", "harvest", "spider"],
    "finance": ["stock", "investment", "trade", "bank", "finance"],
    "medical": ["diagnosis", "treatment", "symptom", "patient", "disease"],
}


def _llm_extract(prompt: str, llm: Optional[str]) -> Tuple[List[str], List[Rule]]:
    """Use an LLM to obtain domains and instructions.

    Parameters
    ----------
    prompt:
        User provided text to analyse.
    llm:
        Preferred LLM provider (``"openai"`` or ``"gemini"``). ``None`` uses the
        first available provider.
    """


    system = (
        "Classify the prompt into domains (scraping, finance, medical, other) "
        "and extract explicit user instructions starting with phrases like "
        "'do not', 'never', or 'avoid'. Respond in JSON with keys 'domains' "
        "(list) and 'instructions' (list of strings). Prompt: {prompt}"
    ).format(prompt=prompt)
    try:
        if (llm in {None, "openai"}) and openai and os.getenv("OPENAI_API_KEY"):

            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": system}],
                temperature=0,
            )
            raw = resp.choices[0].message.content or "{}"
            raw = _strip_code_fence(raw)
        elif (llm in {None, "gemini"}) and genai and os.getenv("GEMINI_API_KEY"):
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel("gemini-2.5-flash")
            res = model.generate_content(system)
            raw = res.text or "{}"
            raw = _strip_code_fence(raw)
        else:
            raise RuntimeError("No LLM credentials available")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - invalid JSON
            LOGGER.warning("LLM joint extraction failed: %s; output=%r", exc, raw)
            data = {}
        domains = data.get("domains") or []
        instructions = data.get("instructions") or []
    except Exception as exc:  # pragma: no cover - network/LLM errors
        LOGGER.warning("LLM joint extraction failed: %s", exc)
        domains, instructions = [], []
    rules = [_build_user_rule(i + 1, inst) for i, inst in enumerate(instructions)]
    return domains, rules


def _heuristic_domains(prompt: str) -> List[str]:
    lowered = prompt.lower()
    hits = [d for d, words in _KEYWORDS.items() if any(w in lowered for w in words)]
    return hits or ["other"]


def _build_user_rule(idx: int, text: str) -> Rule:
    return Rule(
        rule_id=f"USER{idx:03d}",
        description=text,
        type=RuleType.PROCEDURAL,
        severity=SeverityLevel.HIGH,
        domain=ComplianceDomain.OTHER,
        pattern=None,
        llm_instruction=text,
        legal_reference=None,
        example_violation=None,
        index=0,
        category="user",
        action="BLOCK",
        suggestion="Comply with explicit user instruction.",
        source="user",
    )


def _heuristic_instructions(prompt: str) -> List[Rule]:
    pattern = re.compile(r"(?:do not|never|avoid)\s+[^\.]+", re.IGNORECASE)
    matches = pattern.findall(prompt)
    return [_build_user_rule(i + 1, m.strip()) for i, m in enumerate(matches)]


def extract(prompt: str, llm: Optional[str] = None) -> Tuple[List[str], List[Rule]]:
    """Return domains and user rules for ``prompt``.

    Parameters
    ----------
    prompt:
        User provided text to inspect.
    llm:
        Preferred LLM provider. ``None`` chooses the first configured provider.
    """

    if openai or genai:
        domains, rules = _llm_extract(prompt, llm)

        if domains:
            return domains, rules
    domains = _heuristic_domains(prompt)
    rules = _heuristic_instructions(prompt)
    return domains, rules
