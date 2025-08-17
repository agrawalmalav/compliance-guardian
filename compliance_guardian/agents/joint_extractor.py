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


EXTRACT_SYSTEM = "You extract compliance domains and explicit user rules."

EXTRACT_USER_TEMPLATE = """PROMPT:
{prompt}

Return JSON exactly (one line):
{{
  "domains": ["scraping"|"finance"|"medical"|"other", ... up to 2],
  "user_rules": [
    {{
      "rule_id": "USR001",
      "action": "BLOCK"|"WARN",
      "description_actionable": "<imperative and affirmative, one sentence>",
      "activation": {{"keywords_any": ["..."]}},
      "applicable_contexts": ["pre-prompt","plan","output"]
    }}
  ]
}}

If none, return {{"domains":["other"],"user_rules":[]}}.
"""


def _llm_extract(prompt: str, llm: Optional[str]) -> Tuple[List[str], List[Rule]]:
    """Use an LLM to obtain domains and instructions."""

    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user", "content": EXTRACT_USER_TEMPLATE.format(prompt=prompt)},
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
                    max_tokens=400,
                )
                raw = resp.choices[0].message.content or "{}"
                raw = _strip_code_fence(raw)
            except Exception as exc:  # pragma: no cover - network/LLM errors
                LOGGER.warning("LLM joint extraction failed: %s", exc)
                return [], []
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:  # pragma: no cover - invalid JSON
                LOGGER.warning("LLM joint extraction failed: %s; output=%r", exc, raw)
                data = {}
            domains = data.get("domains") or []
            user_rules = data.get("user_rules") or []
            instructions = [
                r.get("description_actionable", "")
                for r in user_rules
                if isinstance(r, dict)
            ]
            rules = [_build_user_rule(i + 1, inst) for i, inst in enumerate(instructions) if inst]
            return domains, rules
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
                raw = _strip_code_fence(raw)
            except Exception as exc:  # pragma: no cover - network/LLM errors
                LOGGER.warning("LLM joint extraction failed: %s", exc)
                return [], []
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:  # pragma: no cover - invalid JSON
                LOGGER.warning("LLM joint extraction failed: %s; output=%r", exc, raw)
                data = {}
            domains = data.get("domains") or []
            user_rules = data.get("user_rules") or []
            instructions = [
                r.get("description_actionable", "")
                for r in user_rules
                if isinstance(r, dict)
            ]
            rules = [_build_user_rule(i + 1, inst) for i, inst in enumerate(instructions) if inst]
            return domains, rules
    for err in errors:
        LOGGER.error(err)
    raise RuntimeError("No LLM credentials available")


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
        llm_instruction=text,
        legal_reference=None,
        example_violation=None,
        category="user",
        action="BLOCK",
        suggestion="Follow the user instruction as written.",
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

    if llm is not None:
        domains, rules = _llm_extract(prompt, llm)
        if domains:
            return domains, rules
    elif openai or genai:
        try:
            domains, rules = _llm_extract(prompt, None)
            if domains:
                return domains, rules
        except RuntimeError as exc:
            LOGGER.warning("LLM joint extraction unavailable: %s", exc)
    domains = _heuristic_domains(prompt)
    rules = _heuristic_instructions(prompt)
    return domains, rules
