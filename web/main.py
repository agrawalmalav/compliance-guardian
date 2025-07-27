"""FastAPI web interface for the Compliance Guardian agents.

This minimal application exposes a simple HTML form that feeds prompts
through the full compliance pipeline. All intermediate results are
rendered so users can inspect the classification, plan, rule checks and
final decision. Audit logs and governance reports can also be downloaded.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from compliance_guardian.agents import (
    compliance_agent,
    domain_classifier,
    primary_agent,
    rule_selector,
)
from compliance_guardian.utils import log_writer
from compliance_guardian.utils.models import AuditLogEntry, PlanSummary


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Compliance Guardian Web")

# Keep a single rule selector instance so rules are cached and auto-reloaded.
_SELECTOR = rule_selector.RuleSelector()

# Expose log and report directories under /static for convenience.
app.mount(
    "/static/logs",
    StaticFiles(directory=log_writer._LOG_DIR),  # type: ignore[attr-defined]
    name="logs-static",
)
app.mount(
    "/static/reports",
    StaticFiles(directory=log_writer._REPORT_DIR),  # type: ignore[attr-defined]
    name="reports-static",
)


class PromptRequest(BaseModel):
    """Request model containing a user prompt."""

    prompt: str


class PipelineResult(BaseModel):
    """Structured summary returned after running the pipeline."""

    prompt: str
    domain: str
    rules: List[str]
    plan: PlanSummary
    plan_allowed: bool
    plan_violation: Optional[AuditLogEntry]
    execution_output: str
    output_allowed: bool
    output_violations: List[AuditLogEntry]
    report_file: Optional[str]


# ---------------------------------------------------------------------------


def _run_pipeline(prompt: str) -> PipelineResult:
    """Run the compliance workflow for ``prompt`` and return details."""

    try:
        domain = domain_classifier.classify_domain(prompt)
    except Exception as exc:  # pragma: no cover - unexpected failure
        LOGGER.exception("Domain classification failed: %s", exc)
        raise HTTPException(status_code=500, detail="Domain classification failed")

    try:
        rules = _SELECTOR.load(domain)
    except Exception as exc:
        LOGGER.exception("Rule loading failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not load compliance rules")

    plan = primary_agent.generate_plan(prompt, domain)

    plan_allowed, plan_entry = compliance_agent.check_plan(plan, rules)

    if plan_allowed:
        execution_output = primary_agent.execute_task(plan, rules, approved=True)
        output_allowed, output_entries = compliance_agent.post_output_check(
            execution_output, rules
        )
    else:
        execution_output = "Execution blocked: plan violates compliance rules"
        output_allowed = False
        output_entries = []

    all_entries: List[AuditLogEntry] = []
    if plan_entry:
        all_entries.append(plan_entry)
    all_entries.extend(output_entries)
    for entry in all_entries:
        log_writer.log_decision(entry)

    report_name: Optional[str] = None
    if all_entries:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        report_name = f"report_{timestamp}.md"
        log_writer.log_session_report(all_entries, report_name)

    return PipelineResult(
        prompt=prompt,
        domain=domain,
        rules=[r.rule_id for r in rules],
        plan=plan,
        plan_allowed=plan_allowed,
        plan_violation=plan_entry,
        execution_output=execution_output,
        output_allowed=output_allowed,
        output_violations=output_entries,
        report_file=report_name,
    )


# ---------------------------------------------------------------------------


def _render_result_html(result: PipelineResult) -> str:
    """Render ``PipelineResult`` as a verbose HTML page."""

    plan_json = result.plan.model_dump_json(indent=2)
    plan_entry = (
        f"<pre>{result.plan_violation.model_dump_json(indent=2)}</pre>"
        if result.plan_violation
        else "<p>No plan violations detected.</p>"
    )
    output_entries = "".join(
        f"<pre>{e.model_dump_json(indent=2)}</pre>" for e in result.output_violations
    )
    report_link = (
        f"<a href='/static/reports/{result.report_file}'>{result.report_file}</a>"
        if result.report_file
        else "No report generated"
    )
    html = f"""
    <html>
      <head><title>Compliance Result</title></head>
      <body>
        <h1>Compliance Pipeline Result</h1>
        <h2>Domain</h2>
        <p>{result.domain}</p>
        <h2>Rules Used</h2>
        <ul>{''.join(f'<li>{r}</li>' for r in result.rules)}</ul>
        <h2>Plan</h2>
        <pre>{plan_json}</pre>
        <h2>Plan Decision</h2>
        {plan_entry}
        <h2>Execution Output</h2>
        <pre>{result.execution_output}</pre>
        <h2>Output Validation</h2>
        <p>Allowed: {result.output_allowed}</p>
        {output_entries or '<p>No post-output violations.</p>'}
        <h2>Governance Report</h2>
        <p>{report_link}</p>
        <p><a href='/'>Submit another prompt</a></p>
      </body>
    </html>
    """
    return html


# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def form() -> str:
    """Return a simple HTML form for entering a prompt."""

    return """
    <html>
      <head><title>Compliance Guardian</title></head>
      <body>
        <h1>Compliance Guardian Demo</h1>
        <form action='/submit' method='post'>
          <textarea name='prompt' rows='4' cols='60'></textarea><br>
          <input type='submit' value='Run Pipeline'>
        </form>
      </body>
    </html>
    """


@app.post("/submit", response_class=HTMLResponse)
async def submit(prompt: str = Form(...)) -> HTMLResponse:
    """Run the pipeline for ``prompt`` and show a detailed result page."""

    result = _run_pipeline(prompt)
    html = _render_result_html(result)
    return HTMLResponse(content=html)


@app.post("/api/submit", response_model=PipelineResult)
async def api_submit(req: PromptRequest) -> PipelineResult:
    """JSON API endpoint mirroring :func:`submit`."""

    return _run_pipeline(req.prompt)


@app.get("/logs", response_class=HTMLResponse)
async def list_logs() -> str:
    """Display available audit log files with download links."""

    log_dir = Path(log_writer._LOG_DIR)  # type: ignore[attr-defined]
    files = sorted(p.name for p in log_dir.glob("*.jsonl"))
    links = "".join(
        f"<li><a href='/static/logs/{name}'>{name}</a></li>" for name in files
    ) or "<li>No logs available</li>"
    return f"<html><body><h1>Audit Logs</h1><ul>{links}</ul></body></html>"


@app.get("/reports", response_class=HTMLResponse)
async def list_reports() -> str:
    """List generated governance reports as hyperlinks."""

    rep_dir = Path(log_writer._REPORT_DIR)  # type: ignore[attr-defined]
    files = sorted(p.name for p in rep_dir.glob("*.md"))
    links = "".join(
        f"<li><a href='/static/reports/{name}'>{name}</a></li>" for name in files
    ) or "<li>No reports available</li>"
    return f"<html><body><h1>Reports</h1><ul>{links}</ul></body></html>"


# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover - manual launch
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
