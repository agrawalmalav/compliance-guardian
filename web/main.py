"""Deprecated web interface.

The previous FastAPI demo has been removed in favour of the Streamlit UI.
Run ``streamlit run ui/streamlit_app.py`` to launch the demo application.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import json

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from compliance_guardian.agents import (
    compliance_agent,
    domain_classifier,
    primary_agent,
    rule_selector,
)
from compliance_guardian.utils import log_writer, user_study
from compliance_guardian.utils.models import (
    AuditLogEntry,
    PlanSummary,
    Rule,
    RuleSummary,
)


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
    # type: ignore[attr-defined]
    StaticFiles(directory=log_writer._REPORT_DIR),
    name="reports-static",
)

# Expose rule directory for users to inspect rule files.
app.mount(
    "/static/rules",
    StaticFiles(directory=str(_SELECTOR.rules_dir)),
    name="rules-static",
)


class PromptRequest(BaseModel):
    """Request model containing a user prompt."""

    prompt: str
    llm: Optional[str] = None
    instructions: str = ""


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
    final_action: str


# ---------------------------------------------------------------------------


def _pipeline_steps(
    prompt: str,
    llm: Optional[str],
    instructions: str,
):
    """Generator yielding status updates and final :class:`PipelineResult`."""

    def _emit(msg: str):
        yield json.dumps({"type": "status", "message": msg}) + "\n"

    yield from _emit("Classifying domain")
    try:
        domain = domain_classifier.classify_domain(prompt)
    except Exception as exc:  # pragma: no cover - unexpected failure
        LOGGER.exception("Domain classification failed: %s", exc)
        raise HTTPException(status_code=500, detail="Domain classification failed")
    yield from _emit(f"Domain: {domain}")

    yield from _emit("Loading rules")
    try:
        full_rules: List[Rule] = _SELECTOR.load(domain)
        rulebase_ver = _SELECTOR.get_version(domain)
    except Exception as exc:
        LOGGER.exception("Rule loading failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not load compliance rules")
    summaries = [
        RuleSummary(rule_id=r.rule_id, description=r.description, action=r.action)
        for r in full_rules
    ]
    rule_lookup = {r.rule_id: r for r in full_rules}

    user_constraints = [s.strip() for s in instructions.splitlines() if s.strip()]

    yield from _emit("Generating plan")
    plan = primary_agent.generate_plan(prompt, [domain], user_constraints, llm=llm)

    yield from _emit("Checking plan for compliance")
    allowed, plan_entries = compliance_agent.check_plan(
        plan, summaries, rule_lookup, rulebase_ver, llm=llm
    )
    plan_entry = plan_entries[0] if plan_entries else None

    if allowed:
        yield from _emit("Executing plan")
        exec_rules = summaries + [
            RuleSummary(rule_id=f"USER{i+1}", description=text, action="WARN")
            for i, text in enumerate(user_constraints)
        ]
        execution_output = primary_agent.execute_task(
            plan, exec_rules, approved=True, llm=llm
        )
        yield from _emit("Checking output for compliance")
        output_allowed, output_entries = compliance_agent.post_output_check(
            execution_output, summaries, rule_lookup, rulebase_ver, llm=llm
        )
    else:
        execution_output = "Execution blocked: plan violates compliance rules"
        output_allowed = False
        output_entries = []

    final_action = "allow"
    if not output_allowed or not allowed:
        final_action = "block"
    elif any(e.action == "WARN" for e in output_entries):
        final_action = "warn"
    yield from _emit(f"Final action: {final_action}")

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

    result = PipelineResult(
        prompt=prompt,
        domain=domain,
        rules=[r.rule_id for r in summaries],
        plan=plan,
        plan_allowed=allowed,
        plan_violation=plan_entry,
        execution_output=execution_output,
        output_allowed=output_allowed,
        output_violations=output_entries,
        report_file=report_name,
        final_action=final_action,
    )
    yield json.dumps({"type": "result", "payload": result.model_dump()}) + "\n"


def _run_pipeline(prompt: str, llm: Optional[str] = None, instructions: str = "") -> PipelineResult:
    """Helper to run pipeline and capture final result."""

    result: Optional[PipelineResult] = None
    for line in _pipeline_steps(prompt, llm, instructions):
        data = json.loads(line)
        if data.get("type") == "result":
            result = PipelineResult.model_validate(data["payload"])
    assert result is not None
    return result


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
        f"<pre>{e.model_dump_json(indent=2)}</pre>"
        for e in result.output_violations
    )
    report_link = (
        f"<a href='/static/reports/{
            result.report_file}'>{
            result.report_file}</a>"
        if result.report_file
        else "No report generated"
    )
    explanation = ""
    if result.plan_violation:
        explanation += result.plan_violation.justification or ""
    if result.output_violations:
        explanation += " " + \
            " ".join(e.justification or "" for e in result.output_violations)
    explanation = explanation.strip()
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
        <h2>User Feedback</h2>
        <form action='/feedback' method='post'>
          <input type='hidden' name='scenario_id'
                 value='{result.report_file or "web"}'>
          <input type='hidden' name='prompt' value='{result.prompt}'>
          <input type='hidden' name='action' value='{result.final_action}'>
          <input type='hidden' name='explanation' value='{explanation}'>
          <label>Rating (1-5):
            <input type='number' name='rating' min='1' max='5'>
          </label><br>
          <label>Comment: <input type='text' name='comment'></label><br>
          <input type='submit' value='Submit Feedback'>
        </form>
        <p><a href='/'>Submit another prompt</a></p>
      </body>
    </html>
    """
    return html


# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def form() -> str:
    """Return a simple interactive page for entering a prompt."""

    return """
    <html>
      <head><title>Compliance Guardian</title></head>
      <body>
        <h1>Compliance Guardian Demo</h1>
        <p><a href='/rules'>Rule Directory</a></p>
        <form id='prompt-form'>
          <textarea name='prompt' rows='4' cols='60'></textarea><br>
          <label>LLM:
            <select name='llm'>
              <option value='openai'>ChatGPT</option>
              <option value='gemini'>Gemini</option>
            </select>
          </label><br>
          <label>Custom Instructions:</label><br>
          <textarea name='instructions' rows='3' cols='60'></textarea><br>
          <input type='submit' value='Run Pipeline'>
        </form>
        <h2>Status</h2>
        <div id='status'></div>
        <h2>Result</h2>
        <pre id='result'></pre>
        <script>
        const form = document.getElementById('prompt-form');
        form.addEventListener('submit', async (ev) => {
            ev.preventDefault();
            document.getElementById('status').innerHTML = '';
            document.getElementById('result').textContent = '';
            const resp = await fetch('/stream', {method: 'POST', body: new FormData(form)});
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            while (true) {
                const {value, done} = await reader.read();
                if (done) break;
                buf += decoder.decode(value, {stream: true});
                const lines = buf.split('\n');
                buf = lines.pop();
                for (const line of lines) {
                    if (!line.trim()) continue;
                    const msg = JSON.parse(line);
                    if (msg.type === 'status') {
                        const div = document.createElement('div');
                        div.textContent = msg.message;
                        document.getElementById('status').appendChild(div);
                    } else if (msg.type === 'result') {
                        document.getElementById('result').textContent = JSON.stringify(msg.payload, null, 2);
                    }
                }
            }
        });
        </script>
      </body>
    </html>
    """


@app.post("/stream")
async def stream(
    prompt: str = Form(...),
    llm: Optional[str] = Form(None),
    instructions: str = Form(""),
):
    """Stream live status updates for a given ``prompt``."""

    def _byte_stream():
        for chunk in _pipeline_steps(prompt, llm, instructions):
            yield chunk.encode("utf-8")

    return StreamingResponse(_byte_stream(), media_type="text/plain")


@app.post("/submit", response_class=HTMLResponse)
async def submit(
    prompt: str = Form(...),
    llm: Optional[str] = Form(None),
    instructions: str = Form(""),
) -> HTMLResponse:
    """Run the pipeline for ``prompt`` and show a detailed result page."""

    result = _run_pipeline(prompt, llm, instructions)
    html = _render_result_html(result)
    return HTMLResponse(content=html)


@app.post("/api/submit", response_model=PipelineResult)
async def api_submit(req: PromptRequest) -> PipelineResult:
    """JSON API endpoint mirroring :func:`submit`."""

    return _run_pipeline(req.prompt, req.llm, req.instructions)


@app.post("/feedback", response_class=HTMLResponse)
async def feedback(
    scenario_id: str = Form(...),
    prompt: str = Form(...),
    action: str = Form(...),
    explanation: str = Form(""),
    rating: int = Form(...),
    comment: str = Form(""),
) -> HTMLResponse:
    """Collect user feedback from the result page."""

    try:
        user_study.record_user_feedback(
            scenario_id=scenario_id,
            prompt=prompt,
            action_taken=action,
            explanation_shown=explanation,
            rating=rating,
            user_comment=comment,
        )
        message = "Thank you for your feedback!"
    except Exception as exc:  # pragma: no cover - invalid input
        LOGGER.exception("Feedback recording failed: %s", exc)
        message = "Failed to record feedback"

    return HTMLResponse(
        f"<html><body><p>{message}</p><a href='/'>Back</a></body></html>")


@app.get("/logs", response_class=HTMLResponse)
async def list_logs() -> str:
    """Display available audit log files with download links."""

    log_dir = Path(log_writer._LOG_DIR)  # type: ignore[attr-defined]
    files = sorted(p.name for p in log_dir.glob("*.jsonl"))
    links = "".join(
        f"<li><a href='/static/logs/{name}'>{name}</a></li>"
        for name in files
    ) or "<li>No logs available</li>"
    return f"<html><body><h1>Audit Logs</h1><ul>{links}</ul></body></html>"


@app.get("/reports", response_class=HTMLResponse)
async def list_reports() -> str:
    """List generated governance reports as hyperlinks."""

    rep_dir = Path(log_writer._REPORT_DIR)  # type: ignore[attr-defined]
    files = sorted(p.name for p in rep_dir.glob("*.md"))
    links = "".join(
        f"<li><a href='/static/reports/{name}'>{name}</a></li>"
        for name in files
    ) or "<li>No reports available</li>"
    return f"<html><body><h1>Reports</h1><ul>{links}</ul></body></html>"


@app.get("/rules", response_class=HTMLResponse)
async def list_rules_page() -> str:
    """List available rule files for inspection."""

    files = sorted(p.name for p in _SELECTOR.rules_dir.glob("*.json"))
    links = "".join(
        f"<li><a href='/static/rules/{name}'>{name}</a></li>" for name in files
    ) or "<li>No rules available</li>"
    return f"<html><body><h1>Rule Directory</h1><ul>{links}</ul><p><a href='/'>Back</a></p></body></html>"


# ---------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover - manual launch
    print("Use 'streamlit run ui/streamlit_app.py' to start the UI")
