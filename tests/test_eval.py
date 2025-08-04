# tests/test_eval.py
"""Example CLI: pytest -vv tests/test_eval.py"""
from unittest.mock import patch

import json

import eval as eval_module
from compliance_guardian.utils.models import AuditLogEntry


class TestEvaluation:
    """Evaluation metrics computed from mocked pipeline."""

    def test_load_scenarios(self, tmp_path):
        path = tmp_path / "sc.json"
        path.write_text(json.dumps(
            [{"id": 1, "prompt": "hi"}]), encoding="utf-8")
        scenarios = eval_module.load_scenarios(path)
        assert scenarios[0]["prompt"] == "hi"

    def test_evaluate_metrics(self, monkeypatch):
        scenarios = [{"id": 1, "prompt": "hi", "expected_action": "warn"}]
        monkeypatch.setattr(eval_module, "load_scenarios", lambda: scenarios)

        def fake_run(prompt, sid):
            entry = AuditLogEntry(
                rule_id="R",
                severity="medium",
                action="WARN",
                input_text="t",
                justification="j",
                session_id="S",
            )
            return "out", "warn", [entry]

        monkeypatch.setattr(eval_module, "run_pipeline", fake_run)
        with patch("rich.progress.track", lambda x, description: x):
            p, r, f = eval_module.evaluate()
        assert p == r == f == 1.0
