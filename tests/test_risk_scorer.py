# tests/test_risk_scorer.py
"""Example CLI: pytest -vv tests/test_risk_scorer.py"""
from compliance_guardian.utils import models, risk_scorer


class TestRiskScorer:
    """Risk score calculations including overrides."""
    def sample_rule(self, severity="high"):
        return models.Rule.model_construct(rule_id="R1", description="desc", type="regex", severity=severity, domain="finance")
    def sample_plan(self):
        return models.PlanSummary.model_construct(action_plan="", goal="", domain="finance", sub_actions=[], original_prompt="")

    def test_default_scores(self):
        rule = self.sample_rule("medium")
        score = risk_scorer.score_risk(rule, self.sample_plan())
        assert score == risk_scorer.DEFAULT_SCORES[models.SeverityLevel.MEDIUM]

    def test_override_matrix(self):
        rule = self.sample_rule("high")
        matrix = {"finance": {"R1": 5}}
        score = risk_scorer.score_risk(rule, self.sample_plan(), matrix)
        assert score == 5

    def test_unknown_severity(self):
        rule = self.sample_rule("low")
        score = risk_scorer.score_risk(rule, self.sample_plan())
        assert score == 10


