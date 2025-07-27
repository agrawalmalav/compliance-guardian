# tests/test_rule_selector.py
"""Example CLI: pytest -vv tests/test_rule_selector.py"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from compliance_guardian.agents import rule_selector
from compliance_guardian.utils.models import Rule


class TestRuleSelector:
    """Exercise rule loading, searching and validation."""

    @pytest.fixture()
    def tmp_rules(self, tmp_path):
        d = tmp_path / "rules"
        d.mkdir()
        data = [
            {
                "rule_id": "T1",
                "description": "Must say foo",
                "type": "content",
                "severity": "low",
                "pattern": "foo",
                "domain": "other",
            }
        ]
        (d / "other.json").write_text(json.dumps(data), encoding="utf-8")
        return d

    def test_strip_comments(self, monkeypatch):
        monkeypatch.setattr(rule_selector, "Observer", MagicMock())
        sel = rule_selector.RuleSelector(rules_dir=Path(".") / "doesnotexist")
        text = "# comment\n/* block */\n{ }// trailing"
        cleaned = sel._strip_comments(text)
        assert "#" not in cleaned
        assert "block" not in cleaned

    def test_load_and_cache(self, tmp_rules, monkeypatch):
        monkeypatch.setattr(rule_selector, "Observer", MagicMock())
        sel = rule_selector.RuleSelector(rules_dir=tmp_rules)
        rules = sel.load("other")
        assert rules and isinstance(rules[0], Rule)
        assert sel.load("other") is rules

    def test_search(self, tmp_rules, monkeypatch):
        monkeypatch.setattr(rule_selector, "Observer", MagicMock())
        sel = rule_selector.RuleSelector(rules_dir=tmp_rules)
        results = sel.search("other", "foo")
        assert results[0].description == "Must say foo"

    def test_validate_errors(self, tmp_rules, monkeypatch):
        monkeypatch.setattr(rule_selector, "Observer", MagicMock())
        bad_file = tmp_rules / "bad.json"
        bad_file.write_text("{ invalid", encoding="utf-8")
        sel = rule_selector.RuleSelector(rules_dir=tmp_rules)
        errors = sel.validate("bad")
        assert errors and "Failed" in errors[0]

    def test_missing_domain(self, tmp_rules, monkeypatch):
        monkeypatch.setattr(rule_selector, "Observer", MagicMock())
        sel = rule_selector.RuleSelector(rules_dir=tmp_rules)
        with pytest.raises(rule_selector.RuleLoadError):
            sel.load("missing")
