import os
from types import SimpleNamespace
from unittest.mock import patch

from compliance_guardian.agents import joint_extractor


def _dummy_openai(output: str) -> SimpleNamespace:
    return SimpleNamespace(
        OpenAI=lambda: SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(content=output)
                            )
                        ]
                    )
                )
            )
        )
    )


def test_joint_extractor_rules():
    prompt = "Please scrape data but do not store emails."
    domains, rules = joint_extractor.extract(prompt)
    assert "scraping" in domains
    assert rules and rules[0].category == "user"


def test_llm_extract_plain_json():
    output = '{"domains": ["scraping"], "instructions": ["never store emails"]}'
    dummy = _dummy_openai(output)
    with patch.dict(os.environ, {"OPENAI_API_KEY": "x"}), patch.object(
        joint_extractor, "openai", dummy
    ):
        domains, rules = joint_extractor._llm_extract("p", llm="openai")
    assert domains == ["scraping"]
    assert [r.description for r in rules] == ["never store emails"]


def test_llm_extract_code_fence():
    fenced = "```json\n{\"domains\": [\"scraping\"], \"instructions\": [\"never store emails\"]}\n```"
    dummy = _dummy_openai(fenced)
    with patch.dict(os.environ, {"OPENAI_API_KEY": "x"}), patch.object(
        joint_extractor, "openai", dummy
    ):
        domains, rules = joint_extractor._llm_extract("p", llm="openai")
    assert domains == ["scraping"]
    assert [r.description for r in rules] == ["never store emails"]
