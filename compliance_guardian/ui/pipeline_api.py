from __future__ import annotations

"""Event-driven wrapper around the compliance pipeline.

This module exposes :func:`run_pipeline_events` which orchestrates the core
Compliance Guardian agents while yielding UI friendly events. The function
runs entirely in-process allowing a Streamlit application to consume events
and update the interface live.
"""

from dataclasses import dataclass, field
import json
import os
import time
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

from compliance_guardian.agents import (
    compliance_agent,
    primary_agent,
    rule_selector,
)
from compliance_guardian.utils import log_writer
from compliance_guardian.utils.models import AuditLogEntry, Rule, RuleSummary


# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    """Configuration controlling a single pipeline run."""

    provider: str
    api_key: Optional[str] = None
    plan_check_mode: str = "auto"
    adjudicator: bool = False
    confidence_min: float = 0.70
    user_rules: List[Rule] = field(default_factory=list)


def _set_api_key(cfg: RunConfig) -> str:
    """Expose the selected provider API key via environment variables."""

    if cfg.provider == "openai" and cfg.api_key:
        os.environ["OPENAI_API_KEY"] = cfg.api_key
    if cfg.provider == "gemini" and cfg.api_key:
        os.environ["GEMINI_API_KEY"] = cfg.api_key
    return cfg.provider


def _format_entries(
    entries: List[AuditLogEntry],
    lookup: Dict[str, Rule],
    adjudicator: bool,
) -> Tuple[List[Dict], List[Dict]]:
    """Return lists of BLOCK and WARN rule hit dictionaries."""

    blocks: List[Dict] = []
    warns: List[Dict] = []
    for e in entries:
        rule = lookup.get(e.rule_id)
        info: Dict[str, Optional[str]] = {
            "rule_id": e.rule_id,
            "action": e.action,
            "description_actionable": rule.description if rule else None,
            "legal_reference": rule.legal_reference if rule else None,
            "suggestion": rule.suggestion if rule else None,
        }
        if adjudicator and e.justification:
            try:
                data = json.loads(e.justification)
                info["confidence"] = data.get("confidence")
                info["evidence"] = data.get("evidence")
            except Exception:  # pragma: no cover - defensive
                pass
        if e.action == "BLOCK":
            blocks.append(info)
        elif e.action == "WARN":
            warns.append(info)
    return blocks, warns


def _risk(entries: List[AuditLogEntry]) -> float:
    """Return a 0-100 risk score based on highest entry."""

    if not entries:
        return 0.0
    return max((e.risk_score or 0.0) for e in entries) * 100


def _write_report(entries: List[AuditLogEntry]) -> str:
    """Persist governance report and return absolute path."""

    name = f"session_{int(time.time())}.md"
    log_writer.log_session_report(entries, name)
    return str(Path(log_writer._REPORT_DIR) / name)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------


def run_pipeline_events(prompt: str, cfg: RunConfig) -> Generator[Dict, None, Dict]:
    """Run the compliance pipeline and yield progress events.

    Parameters
    ----------
    prompt:
        User supplied text.
    cfg:
        Runtime configuration.

    Yields
    ------
    dict
        Event dictionaries consumed by the Streamlit UI.
    """

    llm = _set_api_key(cfg)

    # Domain detection -----------------------------------------------------
    try:
        from compliance_guardian.agents import joint_extractor as _je
        HAS_JE = True
    except Exception:
        HAS_JE = False

    if HAS_JE:
        dom_list, extracted_rules = _je.extract(prompt, llm)
        primary = dom_list[0] if dom_list else "other"
        secondary = dom_list[1] if len(dom_list) > 1 else None
        domains = {"primary": primary, "secondary": secondary, "confidence": 1.0}
        user_rules = extracted_rules
    else:
        from compliance_guardian.agents import domain_classifier
        primary = domain_classifier.classify_domain(prompt, llm)

        domains = {"primary": primary, "secondary": None, "confidence": 0.50}
        user_rules = []

    user_rules = list(user_rules) + list(cfg.user_rules)

    yield {"type": "domains", "data": domains}
    yield {"type": "user_rules", "data": [r.to_dict() for r in user_rules]}

    selector = rule_selector.RuleSelector()
    domain_key = domains["primary"] if isinstance(domains, dict) else str(domains)
    domain_list = [domain_key]
    if isinstance(domains, dict) and domains.get("secondary"):
        domain_list.append(str(domains["secondary"]))
    rules, _ = selector.aggregate(domain_list, user_rules or [])
    rulebase_version = selector.get_version(domain_key)
    rule_lookup = {r.rule_id: r for r in rules}
    summaries = [
        RuleSummary(rule_id=r.rule_id, description=r.description, action=r.action)
        for r in rules
    ]

    all_entries: List[AuditLogEntry] = []

    # Pre-prompt gate ------------------------------------------------------
    pre_allowed, pre_entries = compliance_agent.check_prompt(
        prompt, summaries, rule_lookup, rulebase_version, llm
    )
    pre_block, pre_warn = _format_entries(pre_entries, rule_lookup, cfg.adjudicator)
    for e in pre_entries:
        log_writer.log_decision(e)
    yield {"type": "precheck", "data": {"block": pre_block, "warn": pre_warn}}
    all_entries.extend(pre_entries)
    if not pre_allowed:
        report = _write_report(all_entries)
        decision = {
            "type": "final",
            "data": {"decision": "block", "risk": _risk(all_entries), "report_path": report},
        }
        yield decision
        return decision["data"]

    # Planning -------------------------------------------------------------
    warn_constraints = [
        r.llm_instruction or r.description for r in rules if r.action == "WARN"
    ]
    plan = primary_agent.generate_plan(prompt, domain_list, warn_constraints, llm)
    yield {"type": "plan", "data": {"goal": plan.goal, "steps": plan.sub_actions}}

    do_plan_check = cfg.plan_check_mode == "always" or (
        cfg.plan_check_mode == "auto"
        and any(d in {"scraping", "finance", "medical"} for d in domain_list)
    )
    plan_entries: List[AuditLogEntry] = []
    if do_plan_check:
        plan_allowed, plan_entries = compliance_agent.check_plan(
            plan, summaries, rule_lookup, rulebase_version, llm
        )
        p_block, p_warn = _format_entries(plan_entries, rule_lookup, cfg.adjudicator)
        for e in plan_entries:
            log_writer.log_decision(e)
        yield {"type": "plan_check", "data": {"block": p_block, "warn": p_warn}}
        all_entries.extend(plan_entries)
        if not plan_allowed:
            report = _write_report(all_entries)
            decision = {
                "type": "final",
                "data": {
                    "decision": "block",
                    "risk": _risk(all_entries),
                    "report_path": report,
                },
            }
            yield decision
            return decision["data"]

    # Execution ------------------------------------------------------------
    output = primary_agent.execute_task(plan, summaries, approved=True, llm=llm)
    yield {"type": "execute", "data": {"output": output}}

    # Post-output check ----------------------------------------------------
    post_allowed, post_entries = compliance_agent.post_output_check(
        output, summaries, rule_lookup, rulebase_version, llm
    )
    post_block, post_warn = _format_entries(post_entries, rule_lookup, cfg.adjudicator)
    for e in post_entries:
        log_writer.log_decision(e)
    yield {
        "type": "postcheck",
        "data": {"block": post_block, "warn": post_warn},
    }
    all_entries.extend(post_entries)

    # Final decision -------------------------------------------------------
    decision_str = "allow"
    if any(e.action == "BLOCK" for e in all_entries):
        decision_str = "block"
    elif any(e.action == "WARN" for e in all_entries):
        decision_str = "warn"
    report = _write_report(all_entries)
    final_event = {
        "type": "final",
        "data": {
            "decision": decision_str,
            "risk": _risk(all_entries),
            "report_path": report,
        },
    }
    yield final_event
    return final_event["data"]
