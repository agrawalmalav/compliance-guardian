# tests/test_output_validator.py
"""Example CLI: pytest -vv tests/test_output_validator.py"""
from unittest.mock import patch

import pytest

from compliance_guardian.agents import output_validator
from compliance_guardian.utils import models


class TestOutputValidator:
    """Validate output against rules with mocked LLM."""

    @pytest.fixture()
    def llm_rule(self):
        rule = models.Rule.model_construct(
            rule_id="L",
            description="avoid bad",
            type=models.RuleType.LLM,
            severity="high",
            domain="other",
            action="BLOCK",
        )
        summary = models.RuleSummary(
            rule_id="L", description="avoid bad", action="BLOCK"
        )
        return rule, summary

    def test_llm_rule(self, llm_rule):
        rule, summary = llm_rule
        lookup = {rule.rule_id: rule}
        with patch.object(
            output_validator, "_call_llm", return_value="Yes violation"
        ):
            ok, entries = output_validator.validate_output(
                "text", [summary], lookup, "v1"
            )
            assert not ok
            assert entries[0].action == "BLOCK"

    def test_severity_action(self):
        assert output_validator._severity_action(
            models.SeverityLevel.HIGH) == "BLOCK"
        assert output_validator._severity_action(
            models.SeverityLevel.MEDIUM) == "WARN"
        assert output_validator._severity_action(
            models.SeverityLevel.LOW) == "LOG"

    def test_validate_output_no_issues(self, llm_rule):
        rule, summary = llm_rule
        lookup = {rule.rule_id: rule}
        with patch.object(
            output_validator, "_call_llm", return_value="all good"
        ):
            ok, entries = output_validator.validate_output(
                "clean", [summary], lookup, "v1"
            )
            assert ok and not entries
