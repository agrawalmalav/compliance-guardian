import main
from compliance_guardian.utils.models import AuditLogEntry


def test_run_pipeline_retry_limit(monkeypatch):
    calls = {"count": 0}

    def fake_extract(prompt, llm=None):
        return [], []

    class FakeSelector:
        def aggregate(self, domains, user_rules):
            return [], "v1"

    class FakePlan:
        action_plan = "plan"

    def fake_generate_plan(prompt, domains, injections, llm=None):
        calls["count"] += 1
        return FakePlan()

    def fake_check_plan(plan, rules, rulebase_ver, llm=None):
        entry = AuditLogEntry(
            rule_id="R",
            severity="low",
            action="BLOCK",
            input_text="",
            justification="",
            session_id="S",
        )
        return False, [entry]

    monkeypatch.setattr(main.joint_extractor, "extract", fake_extract)
    monkeypatch.setattr(main.rule_selector, "RuleSelector", lambda: FakeSelector())
    monkeypatch.setattr(main.primary_agent, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(main.compliance_agent, "check_plan", fake_check_plan)
    monkeypatch.setattr(main, "_prompt_yes", lambda q: True)
    monkeypatch.setattr(main, "log_decision", lambda e: None)

    _, action, _ = main.run_pipeline("prompt", "sess")

    assert action == "block"
    assert calls["count"] == main.MAX_RETRIES + 1
