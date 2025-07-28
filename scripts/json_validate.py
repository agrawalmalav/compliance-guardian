#!/usr/bin/env python3
"""Validate and optionally fix JSON-like files."""

import ast
import json
import sys
from pathlib import Path


def fix_file(path: Path) -> None:
    """Validate JSON file at ``path`` and rewrite if necessary."""
    text = path.read_text(encoding="utf-8")
    try:
        json.loads(text)
        print(f"{path} is valid JSON")
        return
    except json.JSONDecodeError as e:
        print(f"{path} invalid JSON: {e}. Attempting to fix...")

    try:
        data = ast.literal_eval(text)
    except Exception as e:  # pragma: no cover - debugging info
        print(f"Failed to parse {path} with ast.literal_eval: {e}")
        raise

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Rewrote {path} with valid JSON")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: json_validate.py <file> [<file> ...]")
        sys.exit(1)
    for arg in sys.argv[1:]:
        fix_file(Path(arg))
