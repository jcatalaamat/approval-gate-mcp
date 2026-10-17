"""Append-only audit log: one JSON line per attempt, including refusals. Params are stored as a digest."""

import json
import time
from pathlib import Path

from .gate import digest


def record(root: Path, tenant: str, operation: str, params: dict, outcome: str, detail: str = "") -> None:
    line = {
        "ts": round(time.time(), 3),
        "tenant": tenant,
        "operation": operation,
        "params_digest": digest(tenant, operation, params or {}),
        "outcome": outcome,
        "detail": detail[:200],
    }
    with open(root / "audit.jsonl", "a") as f:
        f.write(json.dumps(line) + "\n")
