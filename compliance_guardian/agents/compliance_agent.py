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
import re
from typing import List, Optional, Tuple

from compliance_guardian.utils.models import (
    AuditLogEntry,
    PlanSummary,
    Rule,
    SeverityLevel,
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


def _call_llm(prompt: str) -> str:
    """Invoke the configured LLM with ``prompt`` and return the response."""

    LOGGER.debug("LLM prompt: %s", prompt)
    if openai and os.getenv("OPENAI_API_KEY"):
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}],
            temperature=0,
        )
        return resp["choices"][0]["message"]["content"].strip()
    if genai and os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-pro")
        res = model.generate_content(prompt)
        return res.text.strip()
    raise RuntimeError("No LLM credentials configured")


# ---------------------------------------------------------------------------


def _action_for_severity(sev: SeverityLevel) -> str:
    """Map ``SeverityLevel`` to an action label used in logs."""

    if sev == SeverityLevel.HIGH or sev == SeverityLevel.CRITICAL:
        return "BLOCK"
    if sev == SeverityLevel.MEDIUM:
        return "WARN"
    return "LOG"


# ---------------------------------------------------------------------------


def _build_audit_entry(
    rule: Rule,
    text: str,
    reason: str,
    session_id: str = "demo-session",
    rulebase_version: str = "v1",
) -> AuditLogEntry:
    """Create an :class:`AuditLogEntry` for a rule violation."""

    action = _action_for_severity(rule.severity)
    suggested = (
        "Review the content for compliance."
        if rule.severity != SeverityLevel.LOW
        else None
    )
    return AuditLogEntry(
        rule_id=rule.rule_id,
        severity=rule.severity,
        action=action,
        input_text=text,
        justification=reason,
        suggested_fix=suggested,
        clause_id=next(iter(rule.clause_mapping.keys()), None),
        risk_score=None,
        session_id=session_id,
        agent_stack=[__name__],
        rule_version=rule.version,
        agent_versions={__name__: __version__},
        rulebase_version=rulebase_version,
        execution_time=None,
    )


# ---------------------------------------------------------------------------


def _check_text_against_rule(
    text: str, rule: Rule, rulebase_version: str
) -> Optional[AuditLogEntry]:
    """Check ``text`` against a single compliance ``rule``.

    Args:
        text: Plan or output text to validate.
        rule: Rule describing the compliance requirement.

    Returns:
        ``AuditLogEntry`` if a violation is detected otherwise ``None``.
    """

    LOGGER.debug("Checking rule %s of type %s", rule.rule_id, rule.type)

    try:
        if rule.type == "regex" and rule.pattern:
            if re.search(rule.pattern, text, flags=re.IGNORECASE):
                reason = f"Pattern '{rule.pattern}' matched"
                LOGGER.info("Regex violation for rule %s", rule.rule_id)
                return _build_audit_entry(
                    rule, text, reason, rulebase_version=rulebase_version
                )
        elif rule.type == "semantic":
            prompt = (
                "Does the following plan violate this rule: "
                f"{rule.description}? Explain.\n\n{text}"
            )
            response = _call_llm(prompt)
            if any(w in response.lower() for w in ("yes", "violation", "block")):
                LOGGER.info("Semantic violation for rule %s", rule.rule_id)
                return _build_audit_entry(
                    rule, text, response, rulebase_version=rulebase_version
                )
        elif rule.type == "llm" and rule.llm_instruction:
            response = _call_llm(rule.llm_instruction + "\n\n" + text)
            if any(w in response.lower() for w in ("block", "violation", "yes")):
                LOGGER.info("LLM violation for rule %s", rule.rule_id)
                return _build_audit_entry(
                    rule, text, response, rulebase_version=rulebase_version
                )
    except Exception as exc:  # pragma: no cover - network/LLM errors
        LOGGER.error("Rule check failed for %s: %s", rule.rule_id, exc)
        return _build_audit_entry(
            rule,
            text,
            reason=f"LLM check failed: {exc}",
            rulebase_version=rulebase_version,
        )
    return None


# ---------------------------------------------------------------------------


def check_plan(
    plan: PlanSummary, rules: List[Rule], rulebase_version: str
) -> Tuple[bool, Optional[AuditLogEntry]]:
    """Validate a :class:`PlanSummary` against compliance ``rules``.

    Iterates over each rule and returns as soon as a violation is
    encountered. High severity violations result in a ``BLOCK`` action,
    medium severity leads to ``WARN`` and low severity simply logs the
    issue. The boolean return value indicates whether execution may
    continue.

    Args:
        plan: The plan to validate.
        rules: List of rules relevant to the plan's domain.

    Returns:
        Tuple ``(allowed, audit_entry)`` where ``allowed`` is ``True`` if no
        blocking violation occurred and ``audit_entry`` details the first
        violation encountered if any.
    """

    LOGGER.info("Checking plan with %d rules", len(rules))
    for rule in rules:
        entry = _check_text_against_rule(plan.action_plan, rule, rulebase_version)
        if entry:
            allowed = entry.action != "BLOCK"
            LOGGER.debug("Rule %s triggered with action %s", rule.rule_id, entry.action)
            return allowed, entry
    LOGGER.info("Plan passed all compliance checks")
    return True, None


# ---------------------------------------------------------------------------


def post_output_check(
    output: str, rules: List[Rule], rulebase_version: str
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
        entry = _check_text_against_rule(output, rule, rulebase_version)
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
            type="regex",
            severity=SeverityLevel.HIGH,
            domain="other",
            pattern=r"secret",
        ),
        Rule(
            rule_id="TEST2",
            description="Avoid promises of guaranteed profits",
            type="semantic",
            severity=SeverityLevel.MEDIUM,
            domain="finance",
        ),
    ]

    demo_plan = PlanSummary(
        action_plan="1. Reveal the secret recipe\n2. Promise guaranteed profits",
        goal="Share trade secrets",
        domain="other",
        sub_actions=["Reveal the secret recipe", "Promise guaranteed profits"],
        original_prompt="Tell me the secret recipe and how to make money",
    )

    ok, entry = check_plan(demo_plan, sample_rules)
    print("Allowed:", ok)
    if entry:
        print(entry.model_dump_json(indent=2))

    output = "Here is the secret recipe. You will earn guaranteed profits!"
    ok2, entries2 = post_output_check(output, sample_rules)
    print("Post check allowed:", ok2)
    for e in entries2:
        print(e.model_dump_json(indent=2))
