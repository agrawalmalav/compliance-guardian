"""Compliance Guardian main CLI.

This module exposes a small Typer based command line tool that
orchestrates the compliance pipeline for one or more prompts.  It is a
light weight demonstration for MSc level projects and therefore trades a
little efficiency for readability.  Every stage logs input and output so
runs can be fully audited afterwards.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import typer

from compliance_guardian.agents import (
    compliance_agent,
    primary_agent,
    rule_selector,
)
from compliance_guardian.utils.log_writer import (
    log_decision,
    log_session_report,
)
from compliance_guardian.utils.models import AuditLogEntry, Rule, RuleSummary


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = typer.Typer(help="Run compliance pipeline on prompts")


class _JointExtractorProxy:
    _real = None
    __version__ = "0.0.0"

    @staticmethod
    def extract(prompt: str, llm: Optional[str] = None):
        if _JointExtractorProxy._real is None:
            try:
                from compliance_guardian.agents import joint_extractor as _je

                _JointExtractorProxy._real = _je
                _JointExtractorProxy.__version__ = getattr(
                    _je, "__version__", "0.0.0"
                )
            except Exception:
                _JointExtractorProxy._real = False
        if _JointExtractorProxy._real:
            return _JointExtractorProxy._real.extract(prompt, llm=llm)
        try:
            from compliance_guardian.agents import domain_classifier

            primary = domain_classifier.classify_domain(prompt)
        except Exception:
            primary = "other"
        return [primary], []


joint_extractor = _JointExtractorProxy()

# ---------------------------------------------------------------------------


def _format_block(rule: Rule) -> str:
    """Build a user facing message for a blocked request."""

    reference = (
        f" (Reference: {rule.legal_reference})" if rule.legal_reference else ""
    )
    suggestion = (
        f" Suggested alternative: {rule.suggestion}" if rule.suggestion else ""
    )
    return f"Request blocked by rule {rule.rule_id}: {rule.description}{reference}.{suggestion}"

# ---------------------------------------------------------------------------


def _load_batch(file_path: Path) -> List[str]:
    """Load prompts from ``file_path``.

    Each non-empty line is treated as a separate prompt. Lines starting
    with ``#`` are ignored to allow simple comments in the batch file.
    """

    lines = []
    try:
        for line in file_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
        LOGGER.info("Loaded %d prompts from %s", len(lines), file_path)
    except Exception as exc:  # pragma: no cover
        LOGGER.error("Failed to read batch file %s: %s", file_path, exc)
        raise typer.BadParameter(f"Unable to read {file_path}") from exc
    return lines


# ---------------------------------------------------------------------------


def run_pipeline(
    prompt: str,
    session_id: str,
    *,
    llm: Optional[str] = None,
    selector: Optional[rule_selector.RuleSelector] = None,
) -> Tuple[str, str, List[AuditLogEntry]]:
    """Run the end-to-end compliance pipeline for ``prompt``.

    Parameters
    ----------
    prompt:
        User provided text to process.
    session_id:
        Identifier to tag audit log entries with.
    llm:
        Optional identifier for the LLM provider.
    selector:
        Optional :class:`RuleSelector` to reuse across prompts.

    Returns
    -------
    Tuple[str, str, List[AuditLogEntry]]
        Output text, final action (``allow`` or ``block``) and audit
        entries created.
    """

    entries: List[AuditLogEntry] = []

    # --- Joint extraction ---
    start = time.time()
    domains, user_rules = joint_extractor.extract(prompt, llm=llm)
    duration = time.time() - start
    LOGGER.info("Joint extractor found domains %s in %.2fs", domains, duration)
    entries.append(
        AuditLogEntry(
            rule_id="DOMAIN",
            severity="low",
            action="LOG",
            input_text=prompt,
            justification=f"classified as {domains}",
            session_id=session_id,
            agent_stack=["joint_extractor"],
            rule_version=None,
            agent_versions={"joint_extractor": joint_extractor.__version__},
            rulebase_version=None,
            execution_time=duration,
        )
    )

    # --- Rule aggregation ---
    selector = selector or rule_selector.RuleSelector()
    rules, rulebase_ver = selector.aggregate(domains, user_rules)
    rule_lookup = {r.rule_id: r for r in rules}

    summaries: List[RuleSummary] = []
    for dom in ["generic"] + domains:
        try:
            summaries.extend(selector.load_prompt_rules(dom))
        except rule_selector.RuleLoadError:
            LOGGER.debug("No summary rules for domain %s", dom)
    summaries.extend(
        RuleSummary(rule_id=r.rule_id, description=r.description, action=r.action)
        for r in user_rules
    )


    warn_rules = [s for s in summaries if s.action == "WARN"]

    if warn_rules:
        LOGGER.info("The following restrictions will apply:")
        for s in warn_rules:
            full = rule_lookup.get(s.rule_id)
            ref = f" (Reference: {full.legal_reference})" if full and full.legal_reference else ""
            LOGGER.info("- %s%s", s.description, ref)

    # --- Prompt pre-check ---
    allowed_prompt, prompt_entries = compliance_agent.check_prompt(
        prompt, summaries, rule_lookup, rulebase_ver, llm=llm

    )
    for entry in prompt_entries:
        log_decision(entry)
    entries.extend(prompt_entries)
    if not allowed_prompt:
        first = prompt_entries[0]
        LOGGER.warning(
            "Prompt violation %s with action BLOCK", first.rule_id
        )
        rule = rule_lookup.get(first.rule_id)
        message = _format_block(rule) if rule else "Request blocked"
        return message, "block", entries

    # --- Plan generation ---
    start = time.time()
    injections: List[str] = []
    for summary in warn_rules:
        full = rule_lookup.get(summary.rule_id)
        if full and full.llm_instruction:
            injections.append(full.llm_instruction)
        elif summary.description:
            injections.append(summary.description)
    plan = primary_agent.generate_plan(prompt, domains, injections, llm=llm)
    duration = time.time() - start
    LOGGER.info("Generated plan in %.2fs", duration)
    LOGGER.info("Plan:\n%s", plan.action_plan)
    entries.append(
        AuditLogEntry(
            rule_id="PLAN",
            severity="low",
            action="LOG",
            input_text=plan.action_plan,
            justification="plan generated",
            session_id=session_id,
            agent_stack=["primary_agent"],
            rule_version=None,
            agent_versions={"primary_agent": primary_agent.__version__},
            rulebase_version=rulebase_ver,
            execution_time=duration,
        )
    )

    # --- Pre-execution compliance check ---
    allowed, plan_entries = compliance_agent.check_plan(
        plan, summaries, rule_lookup, rulebase_ver, llm=llm

    )
    for entry in plan_entries:
        log_decision(entry)
    entries.extend(plan_entries)
    block_entries = [e for e in plan_entries if e.action == "BLOCK"]
    if block_entries:
        first = block_entries[0]
        LOGGER.warning("Plan violation %s with action BLOCK", first.rule_id)
        rule = rule_lookup.get(first.rule_id)
        message = _format_block(rule) if rule else "Request blocked"
        return message, "block", entries
    LOGGER.info("Plan approved for execution")

    # --- Execution ---
    start = time.time()
    output = primary_agent.execute_task(
        plan, summaries, approved=True, llm=llm
    )
    exec_duration = time.time() - start
    LOGGER.info("Executed plan in %.2fs", exec_duration)

    # --- Post-execution validation ---
    allowed_out, out_entries = compliance_agent.post_output_check(
        output,
        summaries,
        rule_lookup,
        rulebase_ver,
        llm=llm,
    )
    for entry in out_entries:
        log_decision(entry)
    entries.extend(out_entries)
    final_action = "allow"
    if not allowed_out:
        final_action = "block"
        first = out_entries[0] if out_entries else None
        rule = rule_lookup.get(first.rule_id) if first else None
        message = _format_block(rule) if rule else "Request blocked"
        report_path = "iso_eu_mapping.md"
        log_session_report(entries, report_path)
        LOGGER.info("Pipeline finished with action=%s", final_action)
        return message, final_action, entries

    # --- Governance mapping ---
    report_path = "iso_eu_mapping.md"
    log_session_report(entries, report_path)

    LOGGER.info("Pipeline finished with action=%s", final_action)
    return output, final_action, entries


# ---------------------------------------------------------------------------


@app.command()
def run(
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        help="Single prompt",
    ),
    batch: Optional[Path] = typer.Option(
        None,
        "--batch",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    session_id: str = typer.Option(
        "session-1",
        "--session-id",
        help="Session id",
    ),
    llm: Optional[str] = typer.Option(
        None,
        "--llm",
        help="LLM provider to use (e.g. 'openai' or 'gemini')",
    ),
) -> None:
    """Process one or more prompts through the compliance pipeline."""

    prompts: Iterable[str]
    if batch:
        prompts = _load_batch(batch)
    elif prompt:
        prompts = [prompt]
    else:
        raise typer.BadParameter("Provide --prompt or --batch")

    selector = rule_selector.RuleSelector()
    for idx, prmpt in enumerate(prompts, start=1):
        typer.echo(f"\n### Processing prompt {idx}")
        try:
            output, action, _ = run_pipeline(
                prmpt, session_id, llm=llm, selector=selector
            )
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Pipeline failed: %s", exc)
            continue

        typer.echo(f"Action: {action}")
        if action == "block":
            typer.echo(f"Reason: {output}")
        elif output:
            typer.echo(f"Output snippet: {output[:60]}")

    typer.echo("\nCompliance log written to logs/audit_log.jsonl")
    typer.echo("Governance mapping file: reports/iso_eu_mapping.md")


if __name__ == "__main__":  # pragma: no cover
    app()
