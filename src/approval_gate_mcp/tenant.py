"""Tenant context. The tenant is stamped by the server's environment, never taken from a tool argument,
so no operation can name another tenant's data."""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import GateError

TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
DENY_PATTERN = re.compile(r"credential|password|secret|token|\.env(\.|$)", re.IGNORECASE)
MAX_READ_BYTES = 200_000


@dataclass(frozen=True)
class Tenant:
    id: str
    root: Path  # <data_dir>/<tenant>

    @classmethod
    def from_env(cls) -> "Tenant":
        tenant_id = os.environ.get("GATE_TENANT", "")
        data_dir = Path(os.environ.get("GATE_DATA_DIR", "data")).resolve()
        return cls.create(tenant_id, data_dir)

    @classmethod
    def create(cls, tenant_id: str, data_dir: Path) -> "Tenant":
        if not TENANT_RE.match(tenant_id or ""):
            raise GateError("GATE_TENANT must be set to a tenant id like 'acme'")
        root = (Path(data_dir) / tenant_id).resolve()
        if not root.is_dir():
            raise GateError(f"unknown tenant '{tenant_id}'")
        return cls(tenant_id, root)

    @property
    def notes_root(self) -> Path:
        return (self.root / "notes").resolve()

    def resolve_note(self, rel_path: str) -> Path:
        """Relative path inside this tenant's notes folder. Refuses traversal, absolute paths,
        symlink escapes and credential-looking names."""
        if not rel_path or rel_path.startswith(("/", "~")) or ".." in Path(rel_path).parts:
            raise GateError("path must be relative to the tenant's notes folder, e.g. 'plan.md'")
        candidate = (self.notes_root / rel_path).resolve()
        try:
            candidate.relative_to(self.notes_root)
        except ValueError:
            raise GateError("path escapes the tenant's notes folder")
        if DENY_PATTERN.search(candidate.name):
            raise GateError("this file is excluded by the credentials denylist")
        return candidate

    # budget: a hard cap per tenant, re-checked at the moment an action actually runs
    @property
    def budget_file(self) -> Path:
        return self.root / "budget.json"

    def budget(self) -> dict:
        try:
            return json.loads(self.budget_file.read_text())
        except FileNotFoundError:
            return {"cap_cents": 0, "spent_cents": 0}

    def spend(self, amount_cents: int) -> dict:
        b = self.budget()
        remaining = b["cap_cents"] - b["spent_cents"]
        if amount_cents > remaining:
            raise GateError(f"over budget: {amount_cents} cents requested, {remaining} cents remaining")
        b["spent_cents"] += amount_cents
        self.budget_file.write_text(json.dumps(b, indent=2))
        return b
