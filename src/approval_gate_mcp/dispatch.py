"""Transport-agnostic core: operation registry, validation, gate and dispatch."""

import json
import shutil
from pathlib import Path

from . import audit
from .errors import GateError
from .gate import ApprovalGate, digest
from .tenant import MAX_READ_BYTES, Tenant

OPERATIONS_PATH = Path(__file__).resolve().parent.parent.parent / "operations.json"


def load_operations(path: Path = OPERATIONS_PATH) -> dict:
    return json.loads(Path(path).read_text())["operations"]


class Dispatcher:
    def __init__(self, tenant: Tenant, gate: ApprovalGate | None = None, operations: dict | None = None,
                 require_approval: bool = False):
        self.tenant = tenant
        self.require_approval = require_approval
        self.gate = gate or ApprovalGate()
        self.operations = operations or load_operations()
        self.flat = {f"{c}.{a}": op for c, acts in self.operations.items() for a, op in acts.items()}
        self._handlers = {
            "notes.list": self._notes_list,
            "notes.read": self._notes_read,
            "notes.publish": self._notes_publish,
            "spend.balance": self._spend_balance,
            "spend.charge": self._spend_charge,
        }

    # discovery: the model sees three tools, not one per operation
    def discover(self) -> dict:
        return {c: {a: op["description"] for a, op in acts.items()} for c, acts in self.operations.items()}

    def get_schema(self, operation: str) -> dict | None:
        return self.flat.get(operation)

    def execute(self, operation: str, raw_params: dict | None) -> str:
        raw = dict(raw_params or {})
        op = self.flat.get(operation)
        if op is None:
            raise GateError(f"unknown operation '{operation}'; call discover to list operations")
        token = raw.pop("confirm_token", None)
        try:
            if op.get("requires_confirmation"):
                if not token:
                    params = self._validate(op, raw)
                    preview = self.gate.propose(self.tenant.id, operation, params)
                    if self.require_approval:
                        self.tenant.write_proposal(preview["confirm_token"], {"tenant": self.tenant.id, "operation": operation, "params": params})
                        preview["note"] = (
                            "NOT executed. A human must approve this out of band by running "
                            f"`python -m approval_gate_mcp.approve {preview['confirm_token']}`; only then will confirm work."
                        )
                    audit.record(self.tenant.root, self.tenant.id, operation, params, "proposed")
                    return json.dumps(preview, indent=2)
                if self.require_approval:
                    self._check_human_approval(operation, token)
                params = self.gate.confirm(self.tenant.id, operation, token)  # the proposed params, not the resent ones
                if self.require_approval:
                    self.tenant.clear_approval(token)
            else:
                params = self._validate(op, raw)
            result = self._handlers[operation](params)
        except GateError as e:
            audit.record(self.tenant.root, self.tenant.id, operation, raw, "refused", str(e))
            raise
        audit.record(self.tenant.root, self.tenant.id, operation, params, "executed")
        return result

    def _check_human_approval(self, operation: str, token: str) -> None:
        """The approval is bound to a digest of tenant + operation + exact params, written by a separate process."""
        granted = self.tenant.granted_digest(token)
        if granted is None:
            raise GateError("awaiting human approval; the model cannot approve its own action")
        proposal = self.tenant.read_proposal(token)
        if granted != digest(self.tenant.id, operation, proposal["params"]):
            raise GateError("approval does not match the proposed action")

    @staticmethod
    def _validate(op: dict, params: dict) -> dict:
        schema = op["inputSchema"]
        props, required = schema.get("properties", {}), schema.get("required", [])
        missing = [r for r in required if r not in params]
        if missing:
            raise GateError(f"missing required parameter(s): {', '.join(missing)}")
        clean = {k: v for k, v in params.items() if k in props}
        for k, v in clean.items():
            want = props[k].get("type")
            if want == "integer" and (not isinstance(v, int) or isinstance(v, bool)):
                raise GateError(f"'{k}' must be an integer")
            if want == "string" and not isinstance(v, str):
                raise GateError(f"'{k}' must be a string")
        return clean

    # handlers
    def _notes_list(self, p: dict) -> str:
        folder = p.get("folder", ".")
        root = self.tenant.notes_root if folder in (".", "") else self.tenant.resolve_note(folder)
        if not root.is_dir():
            raise GateError("not a folder")
        rows = []
        for child in sorted(root.iterdir()):
            try:
                self.tenant.resolve_note(str(child.relative_to(self.tenant.notes_root)))
            except GateError:
                continue  # denylisted names are hidden from listings, not only from reads
            rows.append({"name": child.name, "type": "dir" if child.is_dir() else "file"})
        return json.dumps(rows, indent=2)

    def _notes_read(self, p: dict) -> str:
        path = self.tenant.resolve_note(p["path"])
        if not path.is_file():
            raise GateError("not a file")
        data = path.read_bytes()
        text = data[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        return text + (f"\n\n...[truncated at {MAX_READ_BYTES} bytes]" if len(data) > MAX_READ_BYTES else "")

    def _notes_publish(self, p: dict) -> str:
        src = self.tenant.resolve_note(p["path"])
        if not src.is_file():
            raise GateError("not a file")
        dest_dir = self.tenant.root / "published"
        dest_dir.mkdir(exist_ok=True)
        shutil.copyfile(src, dest_dir / src.name)
        return json.dumps({"published": src.name})

    def _spend_balance(self, _p: dict) -> str:
        b = self.tenant.budget()
        return json.dumps({**b, "remaining_cents": b["cap_cents"] - b["spent_cents"]})

    def _spend_charge(self, p: dict) -> str:
        if p["amount_cents"] <= 0:
            raise GateError("amount_cents must be greater than 0")
        b = self.tenant.spend(p["amount_cents"])  # cap is enforced here, at execution time
        return json.dumps({"charged_cents": p["amount_cents"], "memo": p["memo"][:120], "remaining_cents": b["cap_cents"] - b["spent_cents"]})
