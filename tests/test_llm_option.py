import main
from compliance_guardian.utils import models


def test_run_pipeline_llm_selection(monkeypatch):
    """Ensure selected LLM provider is propagated through pipeline."""

    def fake_extract(prompt, llm=None):
        assert llm == "openai"
        return ["other"], []

    def fake_generate_plan(prompt, domains, injections, llm=None):
        assert llm == "openai"
        return models.PlanSummary(
            action_plan="step",
            goal="goal",
            domain="other",
            sub_actions=["step"],
            original_prompt=prompt,
        )

    def fake_check_plan(plan, rules, lookup, ver, llm=None):
        assert llm == "openai"
        return True, []

    def fake_execute(plan, rules, approved, llm=None):
        assert llm == "openai"
        return "done"

    def fake_post(output, rules, lookup, ver, llm=None):
        assert llm == "openai"
        return True, []

    class DummySelector:
        def aggregate(self, domains, user_rules):
            return [], "v1"

        def load_prompt_rules(self, domain):
            return []

    monkeypatch.setattr(main.joint_extractor, "extract", fake_extract)
    monkeypatch.setattr(main.primary_agent, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(main.compliance_agent, "check_plan", fake_check_plan)
    monkeypatch.setattr(main.primary_agent, "execute_task", fake_execute)
    monkeypatch.setattr(main.compliance_agent, "post_output_check", fake_post)
    monkeypatch.setattr(main.rule_selector, "RuleSelector", lambda: DummySelector())

    out, action, _ = main.run_pipeline("prompt", "sess", llm="openai")
    assert out == "done"
    assert action == "allow"
