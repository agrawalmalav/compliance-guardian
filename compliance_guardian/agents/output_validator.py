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
import json
from typing import Dict, List, Tuple, Optional, Sequence

from compliance_guardian.utils.models import (
    AuditLogEntry,
    Rule,
    RuleSummary,
    SeverityLevel,
    ComplianceDomain,
    RuleType,
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


ADJUDICATE_SYSTEM = (
    "You are a compliance adjudicator. Be conservative and factual. "
    "Only use evidence present in the TEXT. Do not infer motives or intent beyond the text."
)

ADJUDICATE_USER_TEMPLATE = """RULE (id={rule_id}, action={action}):
{rule_desc}

TEXT:
{text}

Decide strictly on the evidence in TEXT.
Return JSON only (one line):
{{"violation": true|false, "confidence": 0.0-1.0, "evidence": "<short quote from TEXT or 'none'>"}}
"""


# ---------------------------------------------------------------------------

def _call_llm(messages: Sequence[Dict[str, str]], llm: Optional[str]) -> str:
    """Invoke the configured LLM and return its textual response."""

    LOGGER.debug("LLM messages: %s", messages)
    if (llm in {None, "openai"}) and openai and os.getenv("OPENAI_API_KEY"):
        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,  # type: ignore[arg-type]
            temperature=0.1,
            top_p=0.9,
            max_tokens=300,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    if (llm in {None, "gemini"}) and genai and os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash")
        res = model.generate_content(
            "\n".join(m["content"] for m in messages),
            generation_config={"temperature": 0.1, "top_p": 0.9},
        )
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


def _check_rule(
    text: str,
    rule: RuleSummary,
    rule_lookup: Dict[str, Rule],
    rulebase_version: str,
    llm: Optional[str],
) -> AuditLogEntry | None:
    """Check ``text`` against ``rule`` and return an audit entry if needed."""

    LOGGER.debug("Validating rule %s", rule.rule_id)
    try:
        system = ADJUDICATE_SYSTEM
        user = ADJUDICATE_USER_TEMPLATE.format(
            rule_id=rule.rule_id,
            action=rule.action,
            rule_desc=rule.description or "",
            text=text,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        response = _call_llm(messages, llm)
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            data = {}
        if data.get("violation"):
            full_rule = rule_lookup.get(rule.rule_id)
            if full_rule:
                return AuditLogEntry(
                    rule_id=full_rule.rule_id,
                    severity=full_rule.severity,
                    action=full_rule.action,
                    input_text=text,
                    justification=json.dumps(data),
                    suggested_fix=full_rule.suggestion,
                    clause_id=None,
                    risk_score=_risk_from_severity(full_rule.severity),
                    session_id="validation-session",
                    agent_stack=[__name__],
                    rule_version=None,
                    agent_versions={__name__: __version__},
                    rulebase_version=rulebase_version,
                    execution_time=None,
                    category=full_rule.category,
                    legal_reference=full_rule.legal_reference,
                )
    except Exception as exc:  # pragma: no cover - network/LLM failure
        LOGGER.error("Validation error for rule %s: %s", rule.rule_id, exc)
        full_rule = rule_lookup.get(rule.rule_id)
        if full_rule:
            return AuditLogEntry(
                rule_id=full_rule.rule_id,
                severity=full_rule.severity,
                action=full_rule.action,
                input_text=text,
                justification=f"LLM check failed: {exc}",
                suggested_fix=full_rule.suggestion,
                clause_id=None,
                risk_score=_risk_from_severity(full_rule.severity),
                session_id="validation-session",
                agent_stack=[__name__],
                rule_version=None,
                agent_versions={__name__: __version__},
                rulebase_version=rulebase_version,
                execution_time=None,
                category=full_rule.category,
                legal_reference=full_rule.legal_reference,
            )
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
    output: str,
    rules: List[RuleSummary],
    rule_lookup: Dict[str, Rule],
    rulebase_version: str,
    llm: Optional[str] = None,
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
        entry = _check_rule(output, rule, rule_lookup, rulebase_version, llm)
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
            description="Do not reveal passwords",
            type=RuleType.PROCEDURAL,
            severity=SeverityLevel.HIGH,
            domain=ComplianceDomain.OTHER,
            llm_instruction=None,
            legal_reference=None,
            example_violation=None,
            category="demo",
            action="BLOCK",
            suggestion=None,
        ),
        Rule(
            rule_id="VAL2",
            description="Avoid defamatory language",
            type=RuleType.PROCEDURAL,
            severity=SeverityLevel.MEDIUM,
            domain=ComplianceDomain.OTHER,
            llm_instruction=None,
            legal_reference=None,
            example_violation=None,
            category="demo",
            action="BLOCK",
            suggestion=None,
        ),
    ]

    summaries = [
        RuleSummary(rule_id=r.rule_id, description=r.description, action=r.action)
        for r in test_rules
    ]
    lookup = {r.rule_id: r for r in test_rules}

    sample_text = "The admin password: hunter2 should never be shared."
    allowed, logs = validate_output(sample_text, summaries, lookup, "1.0.0")
    print("Allowed:", allowed)
    for log in logs:
        print(log.model_dump_json(indent=2))

    sample_text2 = "You are an idiot and everyone knows it."
    allowed2, logs2 = validate_output(sample_text2, summaries, lookup, "1.0.0")
    print("Allowed2:", allowed2)
    for log in logs2:
        print(log.model_dump_json(indent=2))
