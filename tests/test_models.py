# tests/test_models.py
"""Example CLI: pytest -vv tests/test_models.py"""
import json
import pytest

from compliance_guardian.utils import models


class TestModels:
    """Validate dataclass conversions and error handling."""

    def test_rule_from_to_dict(self):
        data = {
            "rule_id": "R1",
            "description": "desc",
            "type": models.RuleType.SECURITY,
            "severity": models.SeverityLevel.HIGH,
            "domain": models.ComplianceDomain.GDPR,
        }
        rule = models.Rule.from_dict(data)
        assert rule.rule_id == "R1"
        assert rule.to_dict()["rule_id"] == "R1"

    def test_rule_invalid_raises(self):
        with pytest.raises(ValueError):
            models.Rule.from_dict({"rule_id": "R2"})

    def test_audit_log_entry_serialization(self):
        entry = models.AuditLogEntry(
            rule_id="R1",
            severity=models.SeverityLevel.LOW,
            action="LOG",
            input_text="x",
            justification="ok",
            session_id="S1",
        )
        data = entry.to_dict()
        assert data["rule_id"] == "R1"

    def test_session_context_roundtrip(self):
        ctx = models.SessionContext(
            session_id="S", domain="other", user_id="U", risk_threshold=1.0
        )
        recovered = models.SessionContext.from_dict(ctx.to_dict())
        assert recovered.session_id == "S"

    def test_plan_summary_fallbacks(self):
        plan = models.PlanSummary(
            action_plan="do",
            goal="g",
            domain="other",
            sub_actions=["x"],
            original_prompt="p",
        )
        assert "do" in plan.to_dict()["action_plan"]
