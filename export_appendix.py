"""Export experiment artifacts for the dissertation appendix.

This utility collates audit logs, mapping reports, user study feedback and
optionally code coverage/test results. The gathered data is converted into
Markdown, LaTeX or PDF for direct inclusion in an MSc thesis.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

try:
    import pypandoc
except Exception as exc:  # pragma: no cover - runtime dependency
    pypandoc = None
    print(f"Warning: pypandoc unavailable: {exc}", file=sys.stderr)


EXPORT_DIR = Path("exports")
LOG_PATH = Path("logs/audit_log.jsonl")
ISO_MAP_PATH = Path("reports/iso_eu_mapping.md")
USER_STUDY_PATH = Path("reports/user_study.md")
SELF_TEST_PATH = Path("reports/self_test_summary.md")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _load_json_lines(path: Path) -> List[Dict[str, str]]:
    """Load a JSONL file into a list of dictionaries."""

    entries: List[Dict[str, str]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entries.append(json.loads(line))
    except FileNotFoundError:
        print(f"Log file not found: {path}", file=sys.stderr)
    except json.JSONDecodeError as exc:
        print(f"Failed to parse {path}: {exc}", file=sys.stderr)
    return entries


def _build_log_markdown(entries: Iterable[Dict[str, str]]) -> Tuple[str, int]:
    """Convert audit log entries into grouped Markdown tables."""

    if not entries:
        return "", 0

    groups: Dict[str, List[Dict[str, str]]] = {}
    for ent in entries:
        ts = ent.get("timestamp", "")
        day = ts.split("T")[0] if "T" in ts else ts
        groups.setdefault(day, []).append(ent)

    lines = [
        "## Audit Logs",
        f"Exported: {datetime.utcnow().isoformat()} UTC",
        f"Total entries: {len(entries)}",
        "",
    ]
    headers = [
        "timestamp",
        "rule_id",
        "action",
        "justification",
        "session_id",
        "rule_version",
        "rulebase_version",
    ]
    for day, ents in sorted(groups.items()):
        lines.append(f"### {day}")
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for e in ents:
            row = [str(e.get(h, "")) for h in headers]
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    return "\n".join(lines), len(entries)


def _read_markdown(path: Path, title: str) -> Tuple[str, int]:
    """Return file content with a heading if it exists."""

    if not path.exists():
        print(f"Missing file: {path}", file=sys.stderr)
        return "", 0
    text = path.read_text(encoding="utf-8")
    lines_count = len(text.splitlines())
    return f"## {title}\n\n" + text + "\n", lines_count


def _convert_markdown(
    md_text: str,
    out_format: str,
    output_file: Path,
) -> None:
    """Convert Markdown text to ``out_format`` using pandoc."""

    if out_format == "markdown":
        output_file.write_text(md_text, encoding="utf-8")
        return

    if pypandoc is None:
        raise RuntimeError("pypandoc is required for non-Markdown exports")

    if out_format == "pdf":
        pypandoc.convert_text(
            md_text,
            "pdf",
            format="md",
            outputfile=str(output_file),
        )
    else:
        converted = pypandoc.convert_text(md_text, out_format, format="md")
        output_file.write_text(converted, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------


def export_appendix(out_format: str) -> None:
    """Collect available artifacts and export the appendix."""

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ext = (
        "md"
        if out_format == "markdown"
        else ("tex" if out_format == "latex" else "pdf")
    )
    out_file = EXPORT_DIR / f"appendix_export.{ext}"

    md_parts: List[str] = [
        "# MSc Thesis Appendix",
        "This appendix contains logged decisions, compliance mapping tables,",
        "user study feedback and automated test results.",
        "",
    ]

    logs = _load_json_lines(LOG_PATH)
    md_log, log_count = _build_log_markdown(logs)
    if log_count:
        md_parts.append(md_log)

    user_study_md, lines_user = _read_markdown(
        USER_STUDY_PATH,
        "User Study Feedback",
    )
    if lines_user:
        md_parts.append(user_study_md)

    iso_md, lines_iso = _read_markdown(
        ISO_MAP_PATH,
        "ISO/EU Mapping",
    )
    if lines_iso:
        md_parts.append(iso_md)

    self_test_md, lines_test = _read_markdown(
        SELF_TEST_PATH,
        "Self Test Results",
    )
    if lines_test:
        md_parts.append(self_test_md)

    md_content = "\n".join(part.strip() for part in md_parts if part)
    _convert_markdown(md_content, out_format, out_file)

    if log_count:
        log_line = "Exported {} log entries".format(log_count)
    else:
        log_line = "No logs exported"
    summary = [
        log_line,
        f"User study lines: {lines_user}",
        f"ISO mapping lines: {lines_iso}",
        f"Test result lines: {lines_test}",
        f"Output written to {out_file.resolve()}",
    ]
    print("\n".join(summary))


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Export appendix artifacts")
    parser.add_argument(
        "--format",
        choices=["latex", "markdown", "pdf"],
        required=True,
        help="Desired output format",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":  # pragma: no cover - manual execution only
    args = parse_args(sys.argv[1:])
    try:
        export_appendix(args.format)
    except Exception as exc:  # pragma: no cover - catch-all for CLI
        print(f"Export failed: {exc}", file=sys.stderr)
        sys.exit(1)
