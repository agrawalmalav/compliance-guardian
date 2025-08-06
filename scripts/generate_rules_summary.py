#!/usr/bin/env python3
"""Generate lightweight rule summary files from full rule definitions."""

from __future__ import annotations

import json
from pathlib import Path


RULE_DIR = Path(__file__).resolve().parents[1] / "compliance_guardian" / "config" / "rules"
SUMMARY_DIR = RULE_DIR.parent / "rules_summary"


def main() -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    for rule_path in RULE_DIR.glob("*.json"):
        raw = json.loads(rule_path.read_text(encoding="utf-8"))
        entries = raw.get("rules", []) if isinstance(raw, dict) else raw
        summaries = [
            {
                "rule_id": r["rule_id"],
                "description": r.get("description"),
                "action": r.get("action", "LOG"),
            }
            for r in entries
        ]
        out_path = SUMMARY_DIR / rule_path.name
        out_path.write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
