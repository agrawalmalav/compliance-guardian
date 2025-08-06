import main
from compliance_guardian.utils.models import AuditLogEntry


def test_run_pipeline_no_retry(monkeypatch):
    calls = {"count": 0}

    def fake_extract(prompt, llm=None):
        return [], []

    class FakeSelector:
        def aggregate(self, domains, user_rules):
            return [], "v1"

        def load_prompt_rules(self, domain):
            return []

    class FakePlan:
        action_plan = "plan"

    def fake_generate_plan(prompt, domains, injections, llm=None):
        calls["count"] += 1
        return FakePlan()

    def fake_check_plan(plan, rules, lookup, rulebase_ver, llm=None):
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
    monkeypatch.setattr(main, "log_decision", lambda e: None)

    _, action, _ = main.run_pipeline("prompt", "sess")

    assert action == "block"
    assert calls["count"] == 1


def test_run_pipeline_prompt_block(monkeypatch):
    """Ensure prompt violations stop the pipeline immediately."""

    def fake_extract(prompt, llm=None):
        return [], []

    class FakeSelector:
        def aggregate(self, domains, user_rules):
            return [], "v1"

        def load_prompt_rules(self, domain):
            return []

    def fake_check_prompt(prompt, rules, lookup, ver, llm=None):
        entry = AuditLogEntry(
            rule_id="B", severity="high", action="BLOCK", input_text=prompt,
            justification="blocked", session_id="S", legal_reference="L1"
        )
        return False, [entry]

    def fail_generate_plan(*args, **kwargs):  # pragma: no cover
        raise AssertionError("generate_plan should not run")

    monkeypatch.setattr(main.joint_extractor, "extract", fake_extract)
    monkeypatch.setattr(main.rule_selector, "RuleSelector", lambda: FakeSelector())
    monkeypatch.setattr(main.compliance_agent, "check_prompt", fake_check_prompt)
    monkeypatch.setattr(main.primary_agent, "generate_plan", fail_generate_plan)
    monkeypatch.setattr(main, "log_decision", lambda e: None)

    msg, action, _ = main.run_pipeline("bad", "sess")

    assert action == "block"
    assert "Request blocked" in msg
