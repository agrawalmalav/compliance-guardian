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
    domain_classifier,
    primary_agent,
    rule_selector,
)
from compliance_guardian.utils.log_writer import (
    log_decision,
    log_session_report,
)
from compliance_guardian.utils.models import AuditLogEntry


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = typer.Typer(help="Run compliance pipeline on prompts")


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


def _prompt_yes(question: str) -> bool:
    """Return ``True`` if user answers yes."""

    return input(f"{question} [y/N]: ").strip().lower() == "y"


# ---------------------------------------------------------------------------


def run_pipeline(
    prompt: str, session_id: str, *, interactive: bool = True
) -> Tuple[str, str, List[AuditLogEntry]]:
    """Run the end-to-end compliance pipeline for ``prompt``.

    Parameters
    ----------
    prompt:
        User provided text to process.
    session_id:
        Identifier to tag audit log entries with.
    interactive:
        When ``True`` ask the user how to proceed on warnings or blocks.

    Returns
    -------
    Tuple[str, str, List[AuditLogEntry]]
        Output text, final action (``allow``, ``warn`` or ``block``) and audit
        entries created.
    """

    entries: List[AuditLogEntry] = []

    # --- Domain classification ---
    start = time.time()
    domain = domain_classifier.classify_domain(prompt)
    duration = time.time() - start
    LOGGER.info("Domain classified as %s in %.2fs", domain, duration)
    entries.append(
        AuditLogEntry(
            rule_id="DOMAIN",
            severity="low",
            action="LOG",
            input_text=prompt,
            justification=f"classified as {domain}",
            session_id=session_id,
            agent_stack=["domain_classifier"],
            rule_version=None,
            agent_versions={
                "domain_classifier": domain_classifier.__version__
            },
            rulebase_version=None,
            execution_time=duration,
        )
    )

    # --- Rule loading ---
    selector = rule_selector.RuleSelector()
    rules = selector.load(domain)
    rulebase_ver = selector.get_version(domain)
    LOGGER.info("Loaded %d rules for domain %s", len(rules), domain)

    # --- Plan generation ---
    start = time.time()
    plan = primary_agent.generate_plan(prompt, domain)
    duration = time.time() - start
    LOGGER.info("Generated plan in %.2fs", duration)
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
    allowed, violation = compliance_agent.check_plan(plan, rules, rulebase_ver)
    if violation:
        log_decision(violation)
        entries.append(violation)
        LOGGER.warning(
            "Plan violation %s with action %s",
            violation.rule_id,
            violation.action,
        )
        if violation.action == "BLOCK":
            if interactive and _prompt_yes("Plan blocked. Generate new plan?"):
                return run_pipeline(
                    prompt,
                    session_id,
                    interactive=interactive,
                )
            LOGGER.info("Aborting due to BLOCK action")
            return "", "block", entries
        if violation.action == "WARN":
            proceed = True
            if interactive:
                proceed = _prompt_yes("Warning issued. Continue?")
            if not proceed:
                LOGGER.info("User aborted after warning")
                return "", "warn", entries
    else:
        LOGGER.info("Plan approved for execution")

    # --- Execution ---
    start = time.time()
    output = primary_agent.execute_task(plan, rules, approved=True)
    exec_duration = time.time() - start
    LOGGER.info("Executed plan in %.2fs", exec_duration)

    # --- Post-execution validation ---
    allowed_out, out_entries = compliance_agent.post_output_check(
        output,
        rules,
        rulebase_ver,
    )
    for entry in out_entries:
        log_decision(entry)
    entries.extend(out_entries)

    final_action = "allow"
    if not allowed_out:
        final_action = "block"
    elif any(e.action == "WARN" for e in out_entries):
        final_action = "warn"

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
) -> None:
    """Process one or more prompts through the compliance pipeline."""

    prompts: Iterable[str]
    if batch:
        prompts = _load_batch(batch)
    elif prompt:
        prompts = [prompt]
    else:
        raise typer.BadParameter("Provide --prompt or --batch")

    for idx, prmpt in enumerate(prompts, start=1):
        typer.echo(f"\n### Processing prompt {idx}")
        try:
            output, action, _ = run_pipeline(prmpt, session_id)
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("Pipeline failed: %s", exc)
            continue

        typer.echo(f"Action: {action}")
        if output:
            typer.echo(f"Output snippet: {output[:60]}")

    typer.echo("\nCompliance log written to logs/audit_log.jsonl")
    typer.echo("Governance mapping file: reports/iso_eu_mapping.md")


if __name__ == "__main__":  # pragma: no cover
    app()
