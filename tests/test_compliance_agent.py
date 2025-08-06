# tests/test_compliance_agent.py
"""Example CLI: pytest -vv tests/test_compliance_agent.py"""
from unittest.mock import patch

import pytest

from compliance_guardian.agents import compliance_agent
from compliance_guardian.utils import models


class TestComplianceAgent:
    """Check plan and output validation logic."""

    @pytest.fixture()
    def llm_rule(self):
        rule = models.Rule.model_construct(
            rule_id="R",
            description="no foo",
            type=models.RuleType.LLM,
            severity="high",
            domain="other",
            llm_instruction="Does the text mention foo?",
            action="BLOCK",
        )
        summary = models.RuleSummary(
            rule_id="R", description="no foo", action="BLOCK"
        )
        return rule, summary

    @pytest.fixture()
    def semantic_rule(self):
        rule = models.Rule.model_construct(
            rule_id="S",
            description="be nice",
            type=models.RuleType.LLM,
            severity="high",
            domain="other",
            action="BLOCK",
        )
        summary = models.RuleSummary(
            rule_id="S", description="be nice", action="BLOCK"
        )
        return rule, summary

    def test_check_plan_no_violation(self, llm_rule):
        rule, summary = llm_rule
        lookup = {rule.rule_id: rule}
        plan = models.PlanSummary(
            action_plan="bar",
            goal="g",
            domain="other",
            sub_actions=["bar"],
            original_prompt="p",
        )
        with patch.object(
            compliance_agent, "_call_llm", return_value="all good"
        ):
            allowed, entries = compliance_agent.check_plan(
                plan, [summary], lookup, "v1"
            )
            assert allowed and not entries

    def test_check_plan_llm_block(self, llm_rule):
        rule, summary = llm_rule
        lookup = {rule.rule_id: rule}
        plan = models.PlanSummary(
            action_plan="foo",
            goal="g",
            domain="other",
            sub_actions=["foo"],
            original_prompt="p",
        )
        with patch.object(
            compliance_agent, "_call_llm", return_value="block"
        ):
            allowed, entries = compliance_agent.check_plan(
                plan, [summary], lookup, "v1"
            )
            assert not allowed
            assert entries and entries[0].action == "BLOCK"

    def test_check_plan_semantic(self, semantic_rule):
        rule, summary = semantic_rule
        lookup = {rule.rule_id: rule}
        plan = models.PlanSummary(
            action_plan="text",
            goal="g",
            domain="other",
            sub_actions=["x"],
            original_prompt="p",
        )
        with patch.object(
            compliance_agent, "_call_llm", return_value="Yes violation"
        ):
            allowed, entries = compliance_agent.check_plan(
                plan, [summary], lookup, "v1"
            )
            assert not allowed
            assert entries and "violation" in entries[0].justification.lower()

    def test_check_prompt_warn_rule(self):
        rule = models.Rule.model_construct(
            rule_id="W",
            description="no foo",
            type=models.RuleType.LLM,
            severity="medium",
            domain="other",
            action="WARN",
        )
        summary = models.RuleSummary(rule_id="W", description="no foo", action="WARN")
        lookup = {rule.rule_id: rule}
        with patch.object(
            compliance_agent, "_call_llm", return_value="violation found"
        ):
            allowed, entries = compliance_agent.check_prompt(
                "foo", [summary], lookup, "v1"
            )
            assert allowed
            assert entries and entries[0].action == "WARN"

    def test_check_plan_llm_failure(self, semantic_rule):
        rule, summary = semantic_rule
        lookup = {rule.rule_id: rule}
        plan = models.PlanSummary(
            action_plan="text",
            goal="g",
            domain="other",
            sub_actions=["x"],
            original_prompt="p",
        )
        with patch.object(
            compliance_agent,
            "_call_llm",
            side_effect=RuntimeError("boom"),
        ):
            allowed, entries = compliance_agent.check_plan(
                plan, [summary], lookup, "v1"
            )
            assert not allowed
            assert entries and "failed" in entries[0].justification

    def test_post_output_check(self, llm_rule):
        rule, summary = llm_rule
        lookup = {rule.rule_id: rule}
        with patch.object(
            compliance_agent, "_call_llm", return_value="block"
        ):
            allowed, entries = compliance_agent.post_output_check(
                "foo bar", [summary], lookup, "v1"
            )
            assert not allowed
            assert entries and entries[0].rule_id == "R"
