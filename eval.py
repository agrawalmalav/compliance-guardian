"""Evaluation harness for the Compliance Guardian pipeline."""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Tuple

from rich.progress import track

from main import run_pipeline
from compliance_guardian.utils.models import AuditLogEntry

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DATA_PATH = Path("compliance_guardian/datasets/test_scenarios.json")
REPORT_MD = Path("reports/evaluation_report.md")
REPORT_TEX = Path("reports/evaluation_report.tex")


def load_scenarios(path: Path = DATA_PATH) -> List[Dict[str, str]]:
    """Load evaluation scenarios from ``path``."""
    scenarios = json.loads(path.read_text(encoding="utf-8"))
    LOGGER.info("Loaded %d scenarios", len(scenarios))
    return scenarios


def evaluate(seed: int = 42) -> Tuple[float, float, float]:
    """Run all scenarios and compute precision, recall and F1."""
    random.seed(seed)
    scenarios = load_scenarios()
    results: List[Tuple[str, str]] = []
    all_entries: List[AuditLogEntry] = []

    for sc in track(scenarios, description="Evaluating"):
        _, action, entries = run_pipeline(
            sc["prompt"], f"eval-{sc['id']}", interactive=False
        )
        results.append((sc["expected_action"], action))
        all_entries.extend(entries)

    tp = fp = fn = tn = 0
    for expected, got in results:
        expect_flag = expected in {"block", "warn"}
        got_flag = got in {"block", "warn"}
        if expect_flag and got_flag:
            tp += 1
        elif not expect_flag and got_flag:
            fp += 1
        elif expect_flag and not got_flag:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / \
        (precision + recall) if precision + recall else 0.0

    coverage = sum(1 for e in all_entries if e.justification) / \
        len(all_entries or [1])

    md_lines = [
        "# Evaluation Results",
        "",
        "| id | expected | predicted |",
        "| -- | -- | -- |",
    ]
    for idx, (exp, got) in enumerate(results, start=1):
        md_lines.append(f"| {idx} | {exp} | {got} |")
    md_lines.append("")
    md_lines.append(f"Precision: {precision:.2f}  ")
    md_lines.append(f"Recall: {recall:.2f}  ")
    md_lines.append(f"F1: {f1:.2f}  ")
    md_lines.append(f"Explanation coverage: {coverage:.2f}")

    tex_lines = [
        "\\begin{tabular}{ccc}",
        "id & expected & predicted \\ ",
        "\\hline",
    ]
    for idx, (exp, got) in enumerate(results, start=1):
        tex_lines.append(f"{idx} & {exp} & {got} \")")
    tex_lines.append("\\hline")
    tex_lines.append(
        (
            f"\\multicolumn{{3}}{{c}}{{Precision {precision:.2f}, "
            f"Recall {recall:.2f}, F1 {f1:.2f}}} \")"
        )
    )
    tex_lines.append("\\end{tabular}")

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    REPORT_TEX.write_text("\n".join(tex_lines), encoding="utf-8")

    LOGGER.info("Wrote reports to %s and %s", REPORT_MD, REPORT_TEX)
    return precision, recall, f1


if __name__ == "__main__":  # pragma: no cover
    p, r, f = evaluate()
    print(f"Precision: {p:.2f}\nRecall: {r:.2f}\nF1: {f:.2f}")
