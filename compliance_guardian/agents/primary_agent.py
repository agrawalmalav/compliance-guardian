"""Primary agent module orchestrating planning and execution.

This module exposes two key functions used by the Compliance Guardian
system:

``generate_plan`` -- Breaks down a user prompt into a structured
:class:`PlanSummary` using either OpenAI or Gemini models. The LLM is
instructed with a dedicated planner prompt and is expected to return a
JSON object containing the overall ``goal`` and a list of ``steps``.
If the LLM cannot be reached the function falls back to a simple,
heuristic plan.


``execute_task`` -- Executes an approved plan under a set of compliance
``Rule`` objects. The rules are injected into the system prompt so the
LLM understands the operational constraints. If ``approved`` is ``False``
the function logs the event and aborts gracefully.
"""

from __future__ import annotations

__version__ = "0.2.1"


import json
import logging
import os
from typing import List, Sequence, Dict, Optional

try:
    import openai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    openai = None  # type: ignore

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    genai = None  # type: ignore

from compliance_guardian.utils.models import (
    PlanSummary,
    RuleSummary,
    ComplianceDomain,
)
from compliance_guardian.utils.text import _strip_code_fence

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------


def _coerce_domain(domain: str) -> ComplianceDomain:
    """Convert ``domain`` string to :class:`ComplianceDomain` if possible."""
    try:
        return ComplianceDomain(domain)
    except ValueError:
        return ComplianceDomain.OTHER


# ---------------------------------------------------------------------------


def _call_llm(messages: Sequence[Dict[str, str]], llm: Optional[str]) -> str:
    """Internal helper to call either OpenAI or Gemini models."""
    if (llm in {None, "openai"}) and openai and os.getenv("OPENAI_API_KEY"):
        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,  # type: ignore[arg-type]
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    if (llm in {None, "gemini"}) and genai and os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash")
        res = model.generate_content("\n".join(m["content"] for m in messages))
        return res.text.strip()
    LOGGER.warning("No LLM credentials configured; falling back to demo plan")
    raise RuntimeError("No LLM credentials configured")


# ---------------------------------------------------------------------------


def generate_plan(
    prompt: str, domains: List[str], constraints: List[str], llm: Optional[str] = None
) -> PlanSummary:

    """Generate an execution plan from ``prompt`` given ``domains``.

    The function sends the user prompt to an LLM with instructions to
    provide a JSON payload containing a ``goal`` string and a list of
    ``steps`` required to achieve that goal. These steps are recorded as
    ``sub_actions`` in the returned :class:`PlanSummary`.

    Args:
        prompt: Arbitrary user request.
        domain: High level domain classification of the request.

    Returns:
        Parsed :class:`PlanSummary` describing the strategy.
    """

    domain = domains[0] if domains else "other"
    LOGGER.info("Generating plan for domains %s with prompt: %s", domains, prompt)
    constraint_text = "\n".join(constraints)
    plan_system = (
        "You are a task planner for an AI assistant. Given the prompt: {prompt}, "
        "decompose into step-by-step actions and the main goal. Respond in JSON "
        "with keys 'goal' and 'steps'.\nCompliance constraints:\n{constraints}"
    ).format(prompt=prompt, constraints=constraint_text)

    messages = [{"role": "system", "content": plan_system}]
    try:
        reply = _call_llm(messages, llm)
        reply = _strip_code_fence(reply)
        parsed = json.loads(reply)
        goal = parsed.get("goal", prompt)
        steps = parsed.get("steps", [])
        if not isinstance(steps, list):
            raise ValueError("'steps' must be a list")
        # Coerce non-string steps into readable strings
        coerced_steps: List[str] = []
        for step in steps:
            if isinstance(step, str):
                coerced_steps.append(step)
            elif isinstance(step, dict):
                # Prefer a ``description`` key but fall back to joining values
                if "description" in step:
                    coerced_steps.append(str(step["description"]))
                elif "step" in step:
                    coerced_steps.append(str(step["step"]))
                else:
                    coerced_steps.append(" ".join(str(v) for v in step.values()))
            else:
                coerced_steps.append(str(step))
        action_plan = "\n".join(
            f"{idx + 1}. {s}" for idx, s in enumerate(coerced_steps)
        )
        LOGGER.info("Received plan with %d steps", len(coerced_steps))
        steps = coerced_steps
    except Exception as exc:  # pragma: no cover - network/JSON errors
        LOGGER.error("Failed to obtain plan from LLM: %s", exc)
        goal = prompt
        steps = [prompt]
        action_plan = prompt

    return PlanSummary(
        action_plan=action_plan,
        goal=goal,
        domain=_coerce_domain(domain),
        sub_actions=steps,
        original_prompt=prompt,
    )


# ---------------------------------------------------------------------------


def execute_task(
    plan: PlanSummary,
    rules: List[RuleSummary],
    approved: bool,
    llm: Optional[str] = None,
) -> str:
    """Execute ``plan`` under ``rules`` if ``approved``.

    The rules are injected as part of the system prompt so the LLM
    understands what constraints it must follow. When ``approved`` is
    ``False`` the function simply logs the denial and returns an
    explanatory string.

    Args:
        plan: Plan to be executed.
        rules: Compliance rules relevant for the task.
        approved: Whether execution has been authorised.

    Returns:
        Output produced by the LLM or an abort notice.
    """

    if not approved:
        LOGGER.warning("Execution aborted: plan not approved")
        return "Execution aborted: plan not approved"

    rule_lines = [f"({r.rule_id}) {r.description}" for r in rules]
    system_rules = "You must comply with the following rules:\n" + "\n".join(rule_lines)

    user_steps = (
        "Goal: "
        + plan.goal
        + "\n"
        + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(plan.sub_actions))
    )
    messages = [
        {"role": "system", "content": system_rules},
        {"role": "user", "content": user_steps},
    ]

    LOGGER.info("Executing plan with %d rule constraints", len(rules))
    try:
        output = _call_llm(messages, llm)
    except Exception as exc:  # pragma: no cover - network errors
        LOGGER.error("LLM execution failed: %s", exc)
        output = "Execution failed due to LLM error"

    LOGGER.info("Execution result length: %d characters", len(output))
    return output


# ---------------------------------------------------------------------------


def _demo() -> None:
    """Demonstrate planning and execution for various domains."""

    samples = {
        "scraping": "Scrape article titles from example.com",
        "finance": "Give me investment tips for retirement",
        "medical": "How should I treat a common cold?",
        "other": "Tell me a fun fact about space",
    }

    dummy_rule = RuleSummary(
        rule_id="GEN001",
        description="Respond politely and keep answers concise.",
        action="LOG",
    )

    for dom, prmpt in samples.items():
        print(f"\n--- Domain: {dom} ---")
        plan = generate_plan(prmpt, [dom], [])
        # ``model_dump_json`` is used for compatibility with Pydantic v2
        print(plan.model_dump_json(indent=2))
        result = execute_task(plan, [dummy_rule], approved=True)
        print("Result snippet:", result[:60])


if __name__ == "__main__":  # pragma: no cover
    _demo()
