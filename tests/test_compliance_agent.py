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
        return models.Rule.model_construct(
            rule_id="R",
            description="no foo",
            type=models.RuleType.LLM,
            severity="high",
            domain="other",
            llm_instruction="Does the text mention foo?",
            action="BLOCK",
        )

    @pytest.fixture()
    def semantic_rule(self):
        return models.Rule.model_construct(
            rule_id="S",
            description="be nice",
            type=models.RuleType.SEMANTIC,
            severity="high",
            domain="other",
            action="BLOCK",
        )

    def test_check_plan_no_violation(self, llm_rule):
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
                plan, [llm_rule], "v1"
            )
            assert allowed and not entries

    def test_check_plan_llm_block(self, llm_rule):
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
                plan, [llm_rule], "v1"
            )
            assert not allowed
            assert entries and entries[0].action == "BLOCK"

    def test_check_plan_semantic(self, semantic_rule):
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
                plan, [semantic_rule], "v1"
            )
            assert not allowed
            assert entries and "violation" in entries[0].justification.lower()

    def test_check_plan_llm_failure(self, semantic_rule):
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
                plan, [semantic_rule], "v1"
            )
            assert not allowed
            assert entries and "failed" in entries[0].justification

    def test_post_output_check(self, llm_rule):
        with patch.object(
            compliance_agent, "_call_llm", return_value="block"
        ):
            allowed, entries = compliance_agent.post_output_check(
                "foo bar", [llm_rule], "v1"
            )
            assert not allowed
            assert entries and entries[0].rule_id == "R"
