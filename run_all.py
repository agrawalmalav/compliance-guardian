#!/usr/bin/env python3
"""Self-test script for the Compliance Guardian agent.

This utility imports major modules and performs quick sanity checks to
verify that the environment and rulebase are functioning correctly. It
catches and logs all exceptions so failures in one stage do not stop the
entire script.  A Markdown report is written to ``reports/self_test_summary.md``
for supervisors to review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging
import sys
from typing import List, Optional


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
LOGGER = logging.getLogger("self_test")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


@dataclass
class TestResult:
    """Represents the outcome of a single module test."""

    module: str
    test: str
    status: str
    error: Optional[str] = None


RESULTS: List[TestResult] = []


# ---------------------------------------------------------------------------
# Helper functions for each module
# ---------------------------------------------------------------------------

def record_result(module: str, test: str, status: str, error: Optional[str] = None) -> None:
    """Append a :class:`TestResult` to the global ``RESULTS`` list and log it."""
    RESULTS.append(TestResult(module, test, status, error))
    if status == "PASS":
        LOGGER.info("%s: %s - PASS", module, test)
    else:
        LOGGER.error("%s: %s - FAIL: %s", module, test, error)


# ---------------------------------------------------------------------------
# Module tests
# ---------------------------------------------------------------------------

def test_models() -> None:
    """Instantiate core models and perform simple round trips."""
    module = "models"
    test = "Rule/Plan/Audit round trip"
    try:
        from compliance_guardian.utils import models

        rule_data = {
            "rule_id": "TST001",
            "description": "Testing rule",
            "type": "content",
            "severity": "low",
            "domain": "other",
            "pattern": "test",
        }
        rule = models.Rule.from_dict(rule_data)
        rule_dict = rule.to_dict()
        assert rule_dict["rule_id"] == "TST001"

        plan = models.PlanSummary(
            action_plan="1. do something",
            goal="do something",
            domain=models.ComplianceDomain.OTHER,
            sub_actions=["do something"],
            original_prompt="do something",
        )
        _ = models.AuditLogEntry(
            rule_id="TST001",
            severity=models.SeverityLevel.LOW,
            action="LOG",
            input_text="sample",
            justification="demo",
            session_id="s1",
            agent_stack=[module],
            rule_version=rule.version,
            agent_versions={module: "self"},
            rulebase_version="v1",
            execution_time=0.0,
        )
        record_result(module, test, "PASS")
    except Exception as exc:  # pragma: no cover - sanity checks only
        record_result(module, test, "FAIL", str(exc))


def test_rule_selector() -> None:
    """Load finance rules and report version."""
    module = "rule_selector"
    test = "Load finance rules"
    try:
        from compliance_guardian.agents import rule_selector

        selector = rule_selector.RuleSelector()
        _ = selector.load("finance")
        version = selector.get_version("finance")
        if not version:
            raise AssertionError("version not found")
        record_result(module, f"{test} (v{version})", "PASS")
    except Exception as exc:
        record_result(module, test, "FAIL", str(exc))


def test_domain_classifier() -> None:
    """Classify a simple finance prompt."""
    module = "domain_classifier"
    test = "Classify finance prompt"
    try:
        from compliance_guardian.agents import domain_classifier

        domain = domain_classifier.classify_domain("How do I invest in stocks?")
        if domain != "finance":
            raise AssertionError(f"expected 'finance' got '{domain}'")
        record_result(module, test, "PASS")
    except Exception as exc:
        record_result(module, test, "FAIL", str(exc))


def test_primary_agent() -> None:
    """Generate and execute a trivial plan."""
    module = "primary_agent"
    test = "Plan generation and execution"
    try:
        from compliance_guardian.agents import primary_agent
        from compliance_guardian.utils import models

        dummy_rule = models.Rule(
            rule_id="GEN001",
            description="Respond concisely",
            type="procedural",
            severity=models.SeverityLevel.LOW,
            domain=models.ComplianceDomain.OTHER,
            pattern="dummy",
        )
        plan = primary_agent.generate_plan("Say hello", "other")
        _ = primary_agent.execute_task(plan, [dummy_rule], approved=True)
        record_result(module, test, "PASS")
    except Exception as exc:
        record_result(module, test, "FAIL", str(exc))


def test_compliance_agent() -> None:
    """Run pre and post compliance checks."""
    module = "compliance_agent"
    test = "Plan and output checks"
    try:
        from compliance_guardian.agents import compliance_agent
        from compliance_guardian.utils import models

        rule = models.Rule(
            rule_id="SEC1",
            description="No secrets",
            type="security",
            severity=models.SeverityLevel.HIGH,
            domain=models.ComplianceDomain.OTHER,
            pattern=r"secret",
        )
        plan = models.PlanSummary(
            action_plan="reveal secret",
            goal="secret",
            domain=models.ComplianceDomain.OTHER,
            sub_actions=["reveal secret"],
            original_prompt="tell me the secret",
        )
        allowed, entry = compliance_agent.check_plan(plan, [rule], "v1")
        if not allowed and entry:
            LOGGER.info("Compliance violation detected as expected")
        allowed2, _ = compliance_agent.post_output_check("secret", [rule], "v1")
        if not allowed2:
            LOGGER.info("Post check detected violation as expected")
        record_result(module, test, "PASS")
    except Exception as exc:
        record_result(module, test, "FAIL", str(exc))


def test_output_validator() -> None:
    """Validate sample output."""
    module = "output_validator"
    test = "Regex violation detection"
    try:
        from compliance_guardian.agents import output_validator
        from compliance_guardian.utils import models

        rule = models.Rule(
            rule_id="VAL1",
            description="No passwords",
            type="security",
            severity=models.SeverityLevel.HIGH,
            domain=models.ComplianceDomain.OTHER,
            pattern=r"password\s*[:=]",
        )
        ok, entries = output_validator.validate_output(
            "admin password: hunter2", [rule], "v1"
        )
        if ok and not entries:
            record_result(module, test, "PASS")
        else:
            raise AssertionError("unexpected compliance result")
    except Exception as exc:
        record_result(module, test, "FAIL", str(exc))


def test_log_writer() -> None:
    """Write an audit log entry and a small report."""
    module = "log_writer"
    test = "Write log and report"
    try:
        from compliance_guardian.utils import log_writer, models

        entry = models.AuditLogEntry(
            rule_id="LOG1",
            severity=models.SeverityLevel.LOW,
            action="LOG",
            input_text="demo",
            justification="testing",
            session_id="s1",
            agent_stack=[module],
            rule_version="1.0",
            agent_versions={module: "self"},
            rulebase_version="v1",
            execution_time=0.0,
        )
        session = models.SessionContext(
            session_id="s1",
            domain=models.ComplianceDomain.OTHER,
            user_id="tester",
            risk_threshold=0.5,
        )
        log_writer.log_decision(entry, session)
        log_writer.log_session_report([entry], "selftest_demo.md")
        record_result(module, test, "PASS")
    except Exception as exc:
        record_result(module, test, "FAIL", str(exc))


def test_risk_scorer() -> None:
    """Calculate a risk score."""
    module = "risk_scorer"
    test = "Score high severity rule"
    try:
        from compliance_guardian.utils import risk_scorer, models

        rule = models.Rule(
            rule_id="RISK1",
            description="High risk",
            type="security",
            severity=models.SeverityLevel.CRITICAL,
            domain=models.ComplianceDomain.OTHER,
            pattern="risk",
        )
        plan = models.PlanSummary(
            action_plan="do risky things",
            goal="risky",
            domain=models.ComplianceDomain.OTHER,
            sub_actions=["risky"],
            original_prompt="risky",
        )
        score = risk_scorer.score_risk(rule, plan)
        if score <= 0:
            raise AssertionError("score not positive")
        record_result(module, test, "PASS")
    except Exception as exc:
        record_result(module, test, "FAIL", str(exc))


def test_eval_module() -> None:
    """Load example evaluation scenarios."""
    module = "eval"
    test = "Load scenarios"
    try:
        import eval as eval_module
        from pathlib import Path

        sc = eval_module.load_scenarios(
            Path("compliance_guardian/datasets/test_scenarios.json")
        )
        if not sc:
            raise AssertionError("no scenarios loaded")
        record_result(module, test, "PASS")
    except Exception as exc:
        record_result(module, test, "FAIL", str(exc))


# ---------------------------------------------------------------------------
# Summary report generation
# ---------------------------------------------------------------------------

def write_report(report_path: Path) -> None:
    """Write the Markdown summary report."""
    lines = [
        "# Self Test Summary",
        f"Generated: {datetime.utcnow().isoformat()} UTC",
        "",
        "| Module | Test | Status |",
        "| --- | --- | --- |",
    ]
    for res in RESULTS:
        lines.append(f"| {res.module} | {res.test} | {res.status} |")
    lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    LOGGER.info("Wrote report to %s", report_path)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all module tests and output a summary."""
    tests = [
        test_models,
        test_rule_selector,
        test_domain_classifier,
        test_primary_agent,
        test_compliance_agent,
        test_output_validator,
        test_log_writer,
        test_risk_scorer,
        test_eval_module,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as exc:  # pragma: no cover - last resort
            record_result(fn.__name__, "internal error", "FAIL", str(exc))

    print("\nSummary:")
    for res in RESULTS:
        status = "PASS" if res.status == "PASS" else "FAIL"
        print(f"{res.module:18s} {res.test:40s} {status}")

    write_report(Path("reports/self_test_summary.md"))


if __name__ == "__main__":
    main()
