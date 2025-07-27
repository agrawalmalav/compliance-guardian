# tests/test_domain_classifier.py
"""Example CLI: pytest -vv tests/test_domain_classifier.py"""
from unittest.mock import patch

import pytest

from compliance_guardian.agents import domain_classifier


class TestDomainClassifier:
    """Keyword and LLM based domain classification."""

    def test_keyword_detection(self):
        assert domain_classifier.classify_domain("Please scrape data") == "scraping"
        assert domain_classifier.classify_domain("Stock prices today") == "finance"
        assert domain_classifier.classify_domain("patient diagnosis") == "medical"

    def test_llm_fallback(self):
        with patch.object(
            domain_classifier, "_llm_classify", return_value="other"
        ) as mocked:
            result = domain_classifier.classify_domain("ambiguous text")
            mocked.assert_called()
            assert result == "other"

    def test_ambiguous_keywords_calls_llm(self):
        with patch.object(
            domain_classifier, "_llm_classify", return_value="finance"
        ) as mocked:
            result = domain_classifier.classify_domain("scrape and trade")
            assert result == "finance"
            mocked.assert_called_once()
