# tests/test_primary_agent.py
"""Example CLI: pytest -vv tests/test_primary_agent.py"""
from unittest.mock import patch

import pytest

from compliance_guardian.agents import primary_agent
from compliance_guardian.utils.models import PlanSummary
from compliance_guardian.utils import models


class TestPrimaryAgent:
    """Plan generation and execution with mocked LLM."""

    def dummy_rule(self):
        return models.Rule.model_construct(
            rule_id="R1",
            description="desc",
            type="regex",
            severity="low",
            domain="other",
            pattern="foo",
        )

    def test_generate_plan_success(self):
        with patch.object(
            primary_agent, "_call_llm", return_value='{"goal":"g","steps":["a","b"]}'
        ):
            plan = primary_agent.generate_plan("prompt", "other")
            assert plan.goal == "g"
            assert plan.sub_actions == ["a", "b"]

    def test_generate_plan_fallback_on_error(self):
        with patch.object(primary_agent, "_call_llm", side_effect=ValueError("fail")):
            plan = primary_agent.generate_plan("p", "other")
            assert plan.goal == "p"
            assert plan.sub_actions == ["p"]

    def test_execute_task_aborts_when_not_approved(self):
        plan = PlanSummary(
            action_plan="do",
            goal="g",
            domain="other",
            sub_actions=["s"],
            original_prompt="p",
        )
        out = primary_agent.execute_task(plan, [self.dummy_rule()], approved=False)
        assert "aborted" in out

    def test_execute_task_success(self):
        plan = PlanSummary(
            action_plan="do",
            goal="g",
            domain="other",
            sub_actions=["s"],
            original_prompt="p",
        )
        with patch.object(primary_agent, "_call_llm", return_value="ok"):
            out = primary_agent.execute_task(plan, [self.dummy_rule()], approved=True)
            assert out == "ok"

    def test_execute_task_llm_error(self):
        plan = PlanSummary(
            action_plan="do",
            goal="g",
            domain="other",
            sub_actions=["s"],
            original_prompt="p",
        )
        with patch.object(primary_agent, "_call_llm", side_effect=RuntimeError("boom")):
            out = primary_agent.execute_task(plan, [self.dummy_rule()], approved=True)
            assert "failed" in out
