"""Out-of-band approver. A human runs this in a separate terminal (or a separate service does the same job).
It shows the exact proposed action and, on yes, records an approval bound to a digest of tenant + operation + params.
The MCP server exposes no tool that can do this, so the model cannot approve its own action."""

import json
import sys

from .gate import digest
from .tenant import Tenant


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m approval_gate_mcp.approve <confirm_token>", file=sys.stderr)
        return 2
    tenant = Tenant.from_env()
    proposal = tenant.read_proposal(args[0])
    print(f"tenant:    {proposal['tenant']}\noperation: {proposal['operation']}\nparams:    {json.dumps(proposal['params'])}")
    if input("approve this exact action? [y/N] ").strip().lower() != "y":
        print("not approved")
        return 1
    tenant.grant(args[0], digest(proposal["tenant"], proposal["operation"], proposal["params"]))
    print("approved; the agent can now confirm with the same token")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
