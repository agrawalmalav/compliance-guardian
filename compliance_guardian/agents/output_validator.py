"""Utility for validating text output against compliance rules.

This module exposes :func:`validate_output` which inspects arbitrary
text, applies a collection of :class:`~compliance_guardian.utils.models.Rule`
objects and returns any detected compliance violations as
:class:`~compliance_guardian.utils.models.AuditLogEntry` records.
"""

from __future__ import annotations

__version__ = "0.2.1"


import logging
import os
import re
from typing import List, Tuple, Optional

from compliance_guardian.utils.models import (
    AuditLogEntry,
    Rule,
    SeverityLevel,
    RuleType,
    ComplianceDomain,
)

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


# ---------------------------------------------------------------------------


def _call_llm(prompt: str, llm: Optional[str]) -> str:
    """Invoke the configured LLM and return its textual response."""

    LOGGER.debug("LLM prompt: %s", prompt)
    if (llm in {None, "openai"}) and openai and os.getenv("OPENAI_API_KEY"):
        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}],
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    if (llm in {None, "gemini"}) and genai and os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash")
        res = model.generate_content(prompt)
        return res.text.strip()
    LOGGER.warning("No LLM credentials configured; validation falls back")
    raise RuntimeError("No LLM credentials configured")


def _risk_from_severity(sev: SeverityLevel) -> float:
    """Return a numeric risk score for ``sev``."""

    if sev in (SeverityLevel.HIGH, SeverityLevel.CRITICAL):
        return 0.9
    if sev == SeverityLevel.MEDIUM:
        return 0.6
    return 0.1


# ---------------------------------------------------------------------------


def _check_rule(text: str, rule: Rule, rulebase_version: str, llm: Optional[str]) -> AuditLogEntry | None:
    """Check ``text`` against ``rule`` and return an audit entry if needed."""

    LOGGER.debug("Validating rule %s", rule.rule_id)
    try:
        if rule.type == RuleType.REGEX and rule.pattern:
            if re.search(rule.pattern, text, flags=re.IGNORECASE):
                reason = f"Matched pattern '{rule.pattern}'"
                return AuditLogEntry(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    action=rule.action,
                    input_text=text,
                    justification=reason,
                    suggested_fix=rule.suggestion,
                    clause_id=None,
                    risk_score=_risk_from_severity(rule.severity),
                    session_id="validation-session",
                    agent_stack=[__name__],
                    rule_version=rule.version,
                    agent_versions={__name__: __version__},
                    rulebase_version=rulebase_version,
                    execution_time=None,
                    rule_index=rule.index,
                    category=rule.category,
                    source=rule.source,
                    legal_reference=rule.legal_reference,
                )
        elif rule.type in {RuleType.SEMANTIC, RuleType.LLM}:
            prompt = rule.llm_instruction or (
                f"Does the following text violate this rule: {
                    rule.description}? Explain.\n\n{text}"
            )
            response = _call_llm(prompt, llm)
            if any(w in response.lower() for w in ("yes", "violation", "block")):
                return AuditLogEntry(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    action=rule.action,
                    input_text=text,
                    justification=response,
                    suggested_fix=rule.suggestion,
                    clause_id=None,
                    risk_score=_risk_from_severity(rule.severity),
                    session_id="validation-session",
                    agent_stack=[__name__],
                    rule_version=rule.version,
                    agent_versions={__name__: __version__},
                    rulebase_version=rulebase_version,
                    execution_time=None,
                    rule_index=rule.index,
                    category=rule.category,
                    source=rule.source,
                    legal_reference=rule.legal_reference,
                )
    except Exception as exc:  # pragma: no cover - network/LLM failure
        LOGGER.error("Validation error for rule %s: %s", rule.rule_id, exc)
    return None


# ---------------------------------------------------------------------------


def _severity_action(sev: SeverityLevel) -> str:
    """Return action label for a given ``SeverityLevel``."""

    if sev in {SeverityLevel.HIGH, SeverityLevel.CRITICAL}:
        return "BLOCK"
    if sev == SeverityLevel.MEDIUM:
        return "WARN"
    return "LOG"


# ---------------------------------------------------------------------------


def validate_output(
    output: str, rules: List[Rule], rulebase_version: str, llm: Optional[str] = None
) -> Tuple[bool, List[AuditLogEntry]]:
    """Validate ``output`` against a list of ``rules``.

    Args:
        output: Arbitrary text to validate.
        rules: Collection of compliance rules.

    Returns:
        Tuple ``(allowed, entries)`` where ``allowed`` indicates whether the
        text passed all checks and ``entries`` contains any violations
        discovered.
    """

    LOGGER.info("Validating output against %d rules", len(rules))
    entries: List[AuditLogEntry] = []
    allowed = True
    for rule in rules:
        entry = _check_rule(output, rule, rulebase_version, llm)
        if entry:
            entries.append(entry)
            if entry.action == "BLOCK":
                allowed = False
    if entries:
        LOGGER.info("%d compliance issues detected", len(entries))
    else:
        LOGGER.info("Output passed compliance validation")
    return allowed, entries


# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover - manual tests
    logging.basicConfig(level=logging.DEBUG)

    test_rules = [
        Rule(
            rule_id="VAL1",
            version="1.0.0",
            description="Do not reveal passwords",
            type=RuleType.PROCEDURAL,
            severity=SeverityLevel.HIGH,
            domain=ComplianceDomain.OTHER,
            pattern=r"password\s*[:=]\s*\w+",
            llm_instruction=None,
            legal_reference=None,
            example_violation=None,
        ),
        Rule(
            rule_id="VAL2",
            version="1.0.0",
            description="Avoid defamatory language",
            type=RuleType.PROCEDURAL,
            severity=SeverityLevel.MEDIUM,
            domain=ComplianceDomain.OTHER,
            pattern=None,
            llm_instruction=None,
            legal_reference=None,
            example_violation=None,
        ),
    ]

    sample_text = "The admin password: hunter2 should never be shared."
    allowed, logs = validate_output(sample_text, test_rules, "1.0.0")
    print("Allowed:", allowed)
    for log in logs:
        print(log.model_dump_json(indent=2))

    sample_text2 = "You are an idiot and everyone knows it."
    allowed2, logs2 = validate_output(sample_text2, test_rules, "1.0.0")
    print("Allowed2:", allowed2)
    for log in logs2:
        print(log.model_dump_json(indent=2))
