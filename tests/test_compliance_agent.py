# tests/test_compliance_agent.py
"""Example CLI: pytest -vv tests/test_compliance_agent.py"""
from unittest.mock import patch

import pytest

from compliance_guardian.agents import compliance_agent
from compliance_guardian.utils import models


class TestComplianceAgent:
    """Check plan and output validation logic."""

    @pytest.fixture()
    def regex_rule(self):
        return models.Rule.model_construct(
            rule_id="R",
            description="no foo",
            type="regex",
            severity="high",
            domain="other",
            pattern="foo",
        )

    @pytest.fixture()
    def semantic_rule(self):
        return models.Rule.model_construct(
            rule_id="S",
            description="be nice",
            type="semantic",
            severity="high",
            domain="other",
        )

    def test_check_plan_no_violation(self, regex_rule):
        plan = models.PlanSummary(action_plan="bar", goal="g", domain="other", sub_actions=["bar"], original_prompt="p")
        allowed, entry = compliance_agent.check_plan(plan, [regex_rule])
        assert allowed and entry is None

    def test_check_plan_regex_block(self, regex_rule):
        plan = models.PlanSummary(action_plan="foo", goal="g", domain="other", sub_actions=["foo"], original_prompt="p")
        allowed, entry = compliance_agent.check_plan(plan, [regex_rule])
        assert not allowed
        assert entry and entry.action == "BLOCK"

    def test_check_plan_semantic(self, semantic_rule):
        plan = models.PlanSummary(action_plan="text", goal="g", domain="other", sub_actions=["x"], original_prompt="p")
        with patch.object(compliance_agent, "_call_llm", return_value="Yes violation"):
            allowed, entry = compliance_agent.check_plan(plan, [semantic_rule])
            assert not allowed
            assert entry and "violation" in entry.justification.lower()

    def test_check_plan_llm_failure(self, semantic_rule):
        plan = models.PlanSummary(action_plan="text", goal="g", domain="other", sub_actions=["x"], original_prompt="p")
        with patch.object(compliance_agent, "_call_llm", side_effect=RuntimeError("boom")):
            allowed, entry = compliance_agent.check_plan(plan, [semantic_rule])
            assert not allowed
            assert entry and "failed" in entry.justification

    def test_post_output_check(self, regex_rule):
        allowed, entries = compliance_agent.post_output_check("foo bar", [regex_rule])
        assert not allowed
        assert entries and entries[0].rule_id == "R"

