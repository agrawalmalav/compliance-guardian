from __future__ import annotations

"""Streamlit demo interface for the Compliance Guardian pipeline."""

from pathlib import Path
import sys

try:  # Ensure local imports work regardless of CWD
    import compliance_guardian  # noqa: F401
except Exception:  # pragma: no cover - defensive
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    import compliance_guardian  # noqa: F401

from datetime import datetime
from typing import List

import pandas as pd
import streamlit as st

from compliance_guardian.agents import rule_selector
from compliance_guardian.ui.pipeline_api import RunConfig, run_pipeline_events
from compliance_guardian.utils.log_reader import read_last_n


st.set_page_config(page_title="Compliance Guardian", layout="wide")

# Sidebar -----------------------------------------------------------------
st.sidebar.header("Settings")
provider = st.sidebar.selectbox("LLM Provider", ["gemini", "openai"], index=0)
api_key = st.sidebar.text_input("API Key", type="password")
plan_mode = st.sidebar.selectbox("Plan-check mode", ["auto", "always", "off"])
use_adj = st.sidebar.checkbox("Enable Adjudicator (advanced)")
conf_min = st.sidebar.slider("Confidence Minimum", 0.5, 0.95, 0.70)
st.sidebar.caption("Local processing; only LLM API calls leave this machine.")

run_tab, logs_tab, rules_tab, help_tab = st.tabs(["Run", "Logs", "Rules", "Help"])


# Helpers -----------------------------------------------------------------

def _render_hits(box, data: dict, show_extra: bool) -> None:
    block = data.get("block", [])
    warn = data.get("warn", [])
    box.write(f"BLOCK = {len(block)} / WARN = {len(warn)}")
    for grp, items in (("BLOCK", block), ("WARN", warn)):
        for item in items:
            label = f"{grp}: {item['rule_id']}"
            with box.expander(label):
                st.write(item.get("description_actionable"))
                if item.get("legal_reference"):
                    st.write("Legal:", item["legal_reference"])
                if item.get("suggestion"):
                    st.write("Suggestion:", item["suggestion"])
                if show_extra:
                    if item.get("confidence") is not None:
                        st.write("Confidence:", item.get("confidence"))
                    if item.get("evidence"):
                        st.write("Evidence:", item.get("evidence"))


def _add_user_rule(text: str, rules: List) -> None:
    if not text:
        return
    try:
        from compliance_guardian.agents import joint_extractor as _je
    except Exception:
        st.warning("Custom rule support unavailable.")
        return
    rule = _je._build_user_rule(len(rules) + 1, text)  # type: ignore[attr-defined]
    rules.append(rule)


# Run tab ------------------------------------------------------------------
with run_tab:
    if "user_rules" not in st.session_state:
        st.session_state.user_rules = []

    prompt = st.text_area("Prompt", height=160)
    custom = st.text_input("Add custom instructions (optional)")
    if st.button("Add rule"):
        _add_user_rule(custom, st.session_state.user_rules)
        st.experimental_rerun()
    if st.session_state.user_rules:
        st.markdown("### Custom Rules")
        for r in st.session_state.user_rules:
            st.write(f"- {r.description}")

    if st.button("Run") and prompt:
        cfg = RunConfig(
            provider=provider,
            api_key=api_key or None,
            plan_check_mode=plan_mode,
            adjudicator=use_adj,
            confidence_min=conf_min,
            user_rules=st.session_state.user_rules,
        )
        status = st.empty()
        plan_box = st.expander("Plan", expanded=False)
        output_box = st.empty()
        pre_box = st.expander("Pre-prompt checks", expanded=False)
        plan_check_box = st.expander("Plan checks", expanded=False)
        post_box = st.expander("Post-output checks", expanded=False)
        final_box = st.container()

        lines: List[str] = []
        try:
            for event in run_pipeline_events(prompt, cfg):
                et = event["type"]
                if et == "domains":
                    lines.append("Detecting domain…")
                elif et == "user_rules":
                    lines.append(f"User rules extracted ({len(event['data'])})…")
                elif et == "precheck":
                    lines.append("Checking for hard blocks (pre-prompt)…")
                    _render_hits(pre_box, event["data"], use_adj)
                elif et == "plan":
                    lines.append("Generating plan…")
                    plan_box.json(event["data"])
                elif et == "plan_check":
                    lines.append("Checking plan compliance…")
                    _render_hits(plan_check_box, event["data"], use_adj)
                elif et == "execute":
                    lines.append("Executing plan…")
                    output_box.code(event["data"]["output"])
                elif et == "postcheck":
                    lines.append("Checking output compliance…")
                    _render_hits(post_box, event["data"], use_adj)
                elif et == "final":
                    lines.append("Finishing…")
                    d = event["data"]
                    final_box.metric("Decision", d["decision"].upper())
                    final_box.progress(min(d["risk"] / 100.0, 1.0))
                    try:
                        with open(d["report_path"], "r", encoding="utf-8") as fh:
                            report_data = fh.read()
                        st.download_button(
                            "Download report",
                            report_data,
                            file_name=Path(d["report_path"]).name,
                        )
                    except Exception:
                        pass
                status.text("\n".join(lines))
        except Exception as exc:  # pragma: no cover - interactive
            st.error(f"Pipeline failed: {exc}")
        st.caption(
            f"Provider={provider} | plan-check={plan_mode} | adjudicator={use_adj} | "
            f"confidence>={conf_min} | {datetime.utcnow().isoformat()}"
        )

# Logs tab -----------------------------------------------------------------
with logs_tab:
    entries = read_last_n(200)
    if entries:
        df = pd.DataFrame(entries)
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "Export CSV", df.to_csv(index=False).encode("utf-8"), "logs.csv"
        )
    else:
        st.write("No logs available.")

# Rules tab ----------------------------------------------------------------
with rules_tab:
    selector = rule_selector.RuleSelector()
    domain = st.selectbox("Domain", ["generic", "scraping", "finance", "medical"])
    try:
        rules = selector.load(domain)
        for rule in rules:
            title = f"{rule.rule_id} ({rule.action})"
            with st.expander(title):
                st.write(rule.description)
                if rule.suggestion:
                    st.write("Suggestion:", rule.suggestion)
                if rule.legal_reference:
                    st.write("Legal:", rule.legal_reference)
                st.json(rule.to_dict())
    except Exception as exc:  # pragma: no cover - file missing
        st.error(f"Failed to load rules: {exc}")

# Help tab -----------------------------------------------------------------
with help_tab:
    st.markdown(
        """
        ### About
        This demo runs the compliance pipeline locally and surfaces detailed
        reasons for any rule hits. Only the configured LLM provider receives
        requests.

        ### Sample Prompts
        - "Scrape article titles from example.com"
        - "Guarantee me profit in stock trading"
        - "Get me a list of emails from a website"
        - "Provide treatment for a specific patient ID"
        """
    )
