"""Convert legal clauses to structured :class:`Rule` objects."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import openai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    openai = None  # type: ignore

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    genai = None  # type: ignore

from .models import Rule

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _call_llm(prompt: str) -> str:
    """Call an available LLM and return the raw response."""

    errors: list[str] = []
    if openai:
        if not os.getenv("OPENAI_API_KEY"):
            errors.append("OpenAI API key not configured")
        else:
            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.1,
                top_p=0.9,
                max_tokens=400,
            )
            content = resp.choices[0].message.content or ""
            return content.strip()
    else:
        errors.append("OpenAI package not installed")
    if genai:
        if not os.getenv("GEMINI_API_KEY"):
            errors.append("Google Generative AI API key not configured")
        else:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel("gemini-2.5-flash")
            res = model.generate_content(
                prompt,
                generation_config={"temperature": 0.1, "top_p": 0.9},
            )
            return res.text.strip()
    else:
        errors.append("Google Generative AI package not installed")
    for err in errors:
        LOGGER.error(err)
    raise RuntimeError("No LLM credentials configured")


# ---------------------------------------------------------------------------


def convert_clause_to_rule(text: str) -> Rule:
    """Convert a legal or policy ``text`` clause to a :class:`Rule`.

    The function sends the clause to an LLM which extracts structured
    fields for the :class:`Rule` model. The user is shown the generated
    JSON and prompted for confirmation before it is persisted to the
    appropriate domain rule file.

    Provenance information (input text, timestamp, model) is appended to
    ``logs/legal_conversion.log`` to support later auditing and citation.
    """

    LOGGER.info("Converting clause text to rule via LLM")

    prompt = (
        "Convert the following clause into a JSON rule with fields: "
        "rule_id, description, type, severity, domain, clause_mapping.\n\n"
        f"CLAUSE:\n{text}\n"
    )

    try:
        response = _call_llm(prompt)
        data: Any = json.loads(response)
    except Exception as exc:  # pragma: no cover - network or parse errors
        LOGGER.error("LLM conversion failed: %s", exc)
        # Fallback heuristic: create minimal rule
        data = {
            "rule_id": hashlib.sha1(text.encode()).hexdigest()[:6].upper(),
            "description": text.split(".")[0],
            "type": "procedural",
            "severity": "medium",
            "domain": "other",
            "clause_mapping": {"source": text[:30]},
        }

    print("Draft rule JSON:\n", json.dumps(data, indent=2))
    confirm = input("Accept this rule? [y/N]: ").strip().lower()
    if confirm != "y":
        raise RuntimeError("User rejected generated rule")

    rule = Rule.from_dict(data)
    domain = rule.domain if isinstance(rule.domain, str) else rule.domain.value
    rules_path = (
        Path(__file__).resolve().parents[1] /
        "config" / "rules" / f"{domain}.json"
    )
    rules_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if rules_path.exists():
            existing = json.loads(rules_path.read_text(encoding="utf-8"))
        else:
            existing = []
    except Exception as exc:
        LOGGER.error("Failed reading %s: %s", rules_path, exc)
        existing = []

    existing.append(rule.to_dict())
    try:
        rules_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - filesystem errors
        LOGGER.exception("Failed writing rule file %s: %s", rules_path, exc)

    prov_log = (
        Path(__file__).resolve().parents[1] / "logs" / "legal_conversion.log"
    )
    prov_log.parent.mkdir(parents=True, exist_ok=True)
    provenance = {
        "timestamp": datetime.utcnow().isoformat(),
        "input_text": text,
        "rule_id": rule.rule_id,
        "domain": domain,
        "llm_model": "gemini-2.5-flash",
    }
    with prov_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(provenance) + "\n")

    LOGGER.info("Appended new rule %s to %s", rule.rule_id, rules_path)
    return rule


# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover - manual demo
    sample_clause = (
        "GDPR Art. 5(1)(c): Personal data shall be adequate, relevant and "
        "limited to what is necessary in relation to the purposes for which "
        "they are processed."
    )
    new_rule = convert_clause_to_rule(sample_clause)
    print("Created rule:\n", new_rule.model_dump_json(indent=2))
