"""Utilities for collecting user study feedback on compliance decisions."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import typer

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_BASE_DIR = Path(__file__).resolve().parents[1]
_REPORT_FILE = _BASE_DIR / "reports" / "user_study.md"


# ---------------------------------------------------------------------------


def record_user_feedback(
    scenario_id: str,
    prompt: str,
    action_taken: str,
    explanation_shown: str,
    rating: int,
    user_comment: str = "",
) -> None:
    """Record user feedback to ``user_study.md``.

    Parameters
    ----------
    scenario_id:
        Identifier of the evaluation scenario or session.
    prompt:
        Original user prompt that was processed.
    action_taken:
        Final compliance action (allow/warn/block) executed.
    explanation_shown:
        Explanation text presented to the user.
    rating:
        User confidence or satisfaction rating between 1 and 5.
    user_comment:
        Optional free-text feedback from the user.
    """

    if rating < 1 or rating > 5:
        raise ValueError("rating must be between 1 and 5")

    timestamp = datetime.utcnow().isoformat()
    line = (
        f"| {timestamp} | {scenario_id} | {prompt} | {action_taken} | "
        f"{explanation_shown} | {rating} | {user_comment} |"
    )

    header = (
        "| timestamp | scenario_id | prompt | action | explanation | rating | "
        "comment |\n"
        "| --- | --- | --- | --- | --- | --- | --- |"
    )

    try:
        _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        if (
            not _REPORT_FILE.exists()
            or not _REPORT_FILE.read_text(encoding="utf-8").strip()
        ):
            _REPORT_FILE.write_text(header + "\n", encoding="utf-8")
        with _REPORT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        LOGGER.info("Appended feedback to %s", _REPORT_FILE)
    except Exception as exc:  # pragma: no cover - filesystem failures
        LOGGER.exception("Failed to record feedback: %s", exc)
        raise


# ---------------------------------------------------------------------------

app = typer.Typer(help="Collect or append user study feedback")


@app.command()
def collect(
    scenario_id: str = typer.Option(
        ..., "--scenario-id", prompt=True, help="Scenario identifier"
    ),
    prompt: str = typer.Option(
        ..., "--prompt", prompt=True, help="Original prompt"
    ),
    action_taken: str = typer.Option(
        ..., "--action", prompt=True, help="Compliance action taken"
    ),
    explanation_shown: str = typer.Option(
        "",
        "--explanation",
        prompt="Explanation shown",
        help="Explanation presented",
    ),
    rating: int = typer.Option(
        ..., "--rating", prompt=True, min=1, max=5, help="User rating 1-5"
    ),
    user_comment: str = typer.Option(
        "",
        "--comment",
        prompt="Additional comments",
        help="Optional feedback",
    ),
) -> None:
    """CLI entry point for recording a single feedback event."""

    record_user_feedback(
        scenario_id=scenario_id,
        prompt=prompt,
        action_taken=action_taken,
        explanation_shown=explanation_shown,
        rating=rating,
        user_comment=user_comment,
    )


if __name__ == "__main__":  # pragma: no cover - manual invocation
    app()
