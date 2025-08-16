from __future__ import annotations

"""Utility helpers for reading JSONL audit logs."""

import json
from pathlib import Path
from typing import Dict, List

from . import log_writer


def read_last_entries(limit: int = 100) -> List[Dict]:
    """Return the last ``limit`` entries from the audit log.

    Parameters
    ----------
    limit:
        Maximum number of entries to return.
    """

    path = Path(log_writer._LOG_FILE)  # type: ignore[attr-defined]
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
    except Exception:
        return []
    entries: List[Dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
