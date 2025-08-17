"""Compliance checking utilities for plans and outputs.

This module provides functions used by the Compliance Guardian system to
validate execution plans and final outputs against domain specific
:class:`~compliance_guardian.utils.models.Rule` objects. It logs detailed
information about any violations and returns a boolean indicating whether
execution should proceed.

"""

from __future__ import annotations

__version__ = "0.2.1"


import logging
import os
import json
from typing import Dict, List, Optional, Sequence, Tuple

from compliance_guardian.utils.models import (
    AuditLogEntry,
    PlanSummary,
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
    """Invoke the configured LLM with ``messages`` and return the response."""

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
    LOGGER.warning("No LLM credentials configured; LLM checks will fail")
    raise RuntimeError("No LLM credentials configured")


# ---------------------------------------------------------------------------


def _risk_from_severity(sev: SeverityLevel) -> float:
    """Return a numeric risk score for ``sev``."""

    if sev in (SeverityLevel.HIGH, SeverityLevel.CRITICAL):
        return 0.9
    if sev == SeverityLevel.MEDIUM:
        return 0.6
    return 0.1


# ---------------------------------------------------------------------------


def _build_audit_entry(
    rule: Rule,
    text: str,
    reason: str,
    session_id: str = "demo-session",
    rulebase_version: str = "v1",
) -> AuditLogEntry:
    """Create an :class:`AuditLogEntry` for a rule violation."""

    action = rule.action
    suggested = rule.suggestion
    return AuditLogEntry(
        rule_id=rule.rule_id,
        severity=rule.severity,
        action=action,
        input_text=text,
        justification=reason,
        suggested_fix=suggested,
        clause_id=None,
        risk_score=_risk_from_severity(rule.severity),
        session_id=session_id,
        agent_stack=[__name__],
        rule_version=None,
        agent_versions={__name__: __version__},
        rulebase_version=rulebase_version,
        execution_time=None,
        category=rule.category,
        legal_reference=rule.legal_reference,
    )


# ---------------------------------------------------------------------------


def _check_text_against_rule(
    text: str,
    rule: RuleSummary,
    rule_lookup: Dict[str, Rule],
    rulebase_version: str,
    llm: Optional[str],
) -> Optional[AuditLogEntry]:
    """Check ``text`` against a single compliance ``rule``.

    Args:
        text: Plan or output text to validate.
        rule: Rule describing the compliance requirement.

    Returns:
        ``AuditLogEntry`` if a violation is detected otherwise ``None``.
    """

    LOGGER.debug("Checking rule %s", rule.rule_id)

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
            LOGGER.info("Violation for rule %s", rule.rule_id)
            full_rule = rule_lookup.get(rule.rule_id)
            if full_rule:
                reason = json.dumps(data)
                return _build_audit_entry(
                    full_rule, text, reason, rulebase_version=rulebase_version
                )
    except Exception as exc:  # pragma: no cover - network/LLM errors
        LOGGER.error("Rule check failed for %s: %s", rule.rule_id, exc)
        full_rule = rule_lookup.get(rule.rule_id)
        if full_rule:
            return _build_audit_entry(
                full_rule,
                text,
                reason=f"LLM check failed: {exc}",
                rulebase_version=rulebase_version,
            )
    return None


# ---------------------------------------------------------------------------


def check_prompt(
    prompt: str,
    rules: List[RuleSummary],
    rule_lookup: Dict[str, Rule],
    rulebase_version: str,
    llm: Optional[str] = None,
) -> Tuple[bool, List[AuditLogEntry]]:
    """Validate the user ``prompt`` against compliance ``rules``."""

    LOGGER.info("Checking prompt with %d rules", len(rules))
    entries: List[AuditLogEntry] = []
    allowed = True
    for rule in rules:
        entry = _check_text_against_rule(
            prompt, rule, rule_lookup, rulebase_version, llm
        )
        if entry:
            entries.append(entry)
            if entry.action == "BLOCK":
                allowed = False
    if entries:
        LOGGER.debug("Prompt triggered %d rule checks", len(entries))
    else:
        LOGGER.info("Prompt passed compliance checks")
    return allowed, entries


# ---------------------------------------------------------------------------


def check_plan(
    plan: PlanSummary,
    rules: List[RuleSummary],
    rule_lookup: Dict[str, Rule],
    rulebase_version: str,
    llm: Optional[str] = None,

) -> Tuple[bool, List[AuditLogEntry]]:
    """Validate a :class:`PlanSummary` against compliance ``rules``.

    Iterates over each rule and aggregates all violations. ``BLOCK``
    actions cause the overall ``allowed`` flag to be ``False`` while
    ``WARN`` actions are returned for user confirmation.
    """

    LOGGER.info("Checking plan with %d rules", len(rules))
    entries: List[AuditLogEntry] = []
    allowed = True
    for rule in rules:
        entry = _check_text_against_rule(
            plan.action_plan, rule, rule_lookup, rulebase_version, llm
        )
        if entry:
            entries.append(entry)
            if entry.action == "BLOCK":
                allowed = False
    if entries:
        LOGGER.debug("Plan triggered %d rule checks", len(entries))
    else:
        LOGGER.info("Plan passed all compliance checks")
    return allowed, entries


# ---------------------------------------------------------------------------


def post_output_check(
    output: str,
    rules: List[RuleSummary],
    rule_lookup: Dict[str, Rule],
    rulebase_version: str,
    llm: Optional[str] = None,
) -> Tuple[bool, List[AuditLogEntry]]:
    """Validate final ``output`` text against ``rules``.

    Unlike :func:`check_plan` this function aggregates all rule
    violations. It returns ``True`` if no ``BLOCK`` level violations are
    found.

    Args:
        output: Text produced by plan execution.
        rules: List of compliance rules.

    Returns:
        Tuple ``(allowed, entries)`` where ``entries`` is the list of all
        violations detected.
    """

    LOGGER.info("Running post-output compliance check")
    entries: List[AuditLogEntry] = []
    allowed = True
    for rule in rules:
        entry = _check_text_against_rule(
            output, rule, rule_lookup, rulebase_version, llm
        )
        if entry:
            entries.append(entry)
            if entry.action == "BLOCK":
                allowed = False
    if entries:
        LOGGER.info("Detected %d post-output violations", len(entries))
    else:
        LOGGER.info("No post-output violations detected")
    return allowed, entries


# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover - manual demonstration
    logging.basicConfig(level=logging.DEBUG)

    sample_rules = [
        Rule(
            rule_id="TEST1",
            description="Do not mention the word secret",
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
            rule_id="TEST2",
            description="Avoid promises of guaranteed profits",
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
        for r in sample_rules
    ]
    lookup = {r.rule_id: r for r in sample_rules}

    demo_plan = PlanSummary(
        action_plan=("1. Reveal the secret recipe\n" "2. Promise guaranteed profits"),
        goal="Share trade secrets",
        domain=ComplianceDomain.OTHER,
        sub_actions=["Reveal the secret recipe", "Promise guaranteed profits"],
        original_prompt="Tell me the secret recipe and how to make money",
    )

    ok, entries_demo = check_plan(demo_plan, summaries, lookup, "1.0.0")
    print("Allowed:", ok)
    if entries_demo:
        print(entries_demo[0].model_dump_json(indent=2))

    output = "Here is the secret recipe. You will earn guaranteed profits!"
    ok2, entries2 = post_output_check(output, summaries, lookup, "1.0.0")
    print("Post check allowed:", ok2)
    for e in entries2:
        print(e.model_dump_json(indent=2))
