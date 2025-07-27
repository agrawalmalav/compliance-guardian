# tests/test_log_writer.py
"""Example CLI: pytest -vv tests/test_log_writer.py"""
import json
from pathlib import Path

import pytest

from compliance_guardian.utils import log_writer, models


class TestLogWriter:
    """Ensure audit logging utilities create files correctly."""

    @pytest.fixture()
    def paths(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        report_dir = tmp_path / "reports"
        monkeypatch.setattr(log_writer, "_LOG_DIR", log_dir)
        monkeypatch.setattr(log_writer, "_REPORT_DIR", report_dir)
        monkeypatch.setattr(log_writer, "_LOG_FILE", log_dir / "audit_log.jsonl")
        return log_dir, report_dir

    def sample_entry(self):
        return models.AuditLogEntry(
            rule_id="R1",
            severity="low",
            action="LOG",
            input_text="txt",
            justification="ok",
            session_id="S",
        )

    def sample_session(self):
        return models.SessionContext(
            session_id="S",
            domain="other",
            user_id="u",
            risk_threshold=0.0,
        )

    def test_log_decision_writes_file(self, paths):
        log_dir, _ = paths
        entry = self.sample_entry()
        log_writer.log_decision(entry, self.sample_session())
        data = json.loads((log_dir / "audit_log.jsonl").read_text())
        assert data["rule_id"] == "R1"
        assert "run_hash" in data

    def test_log_session_report(self, paths):
        _, report_dir = paths
        entry = self.sample_entry()
        log_writer.log_session_report([entry], "report.md")
        content = (report_dir / "report.md").read_text()
        assert "ISO/EU" in content


    def test_rotate_logs(self, paths, monkeypatch):
        log_dir, _ = paths
        log_file = log_dir / "audit_log.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("x" * 2)
        monkeypatch.setattr(log_writer, "_LOG_SIZE_LIMIT", 1)
        log_writer._rotate_logs()
        rotated = list(log_dir.glob("audit_log_*.jsonl"))
        assert rotated and rotated[0].exists()

