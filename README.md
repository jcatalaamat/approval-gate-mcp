# approval-gate-mcp

A small [MCP](https://modelcontextprotocol.io) server that shows three things an agent platform needs before it touches real systems:

1. **On-demand discovery.** The model sees three tools (`discover`, `get_schema`, `execute`), not one tool per operation. Adding an operation means adding an entry to `operations.json`; the model's context does not grow.
2. **Tenant isolation by construction.** The tenant is stamped from the server's environment (`GATE_TENANT`). No tool takes a tenant argument, so no call can name another tenant's data. Paths are confined to the tenant's folder (traversal, absolute paths and symlink escapes are refused), credential-looking files are unreadable and hidden from listings, and there is deliberately no search operation.
3. **A real approval gate, approved out of band.** Operations marked `requires_confirmation` do nothing on the first call. They return a preview and a one-time token. The second call must present that token, and what runs is the action that was *proposed*, not whatever params arrive with the token. Tokens are bound to the tenant and operation that minted them, are single use, and expire after 10 minutes. With `GATE_REQUIRE_APPROVAL=1` (the default for the server) the token alone is not enough: a human must run `python -m approval_gate_mcp.approve <token>` in a separate process, which shows the exact params and records an approval bound to a digest of tenant + operation + params. The MCP server exposes no tool that can grant approval, so the model cannot approve its own action.

On top of that: a hard per-tenant **budget cap** that is re-checked at the moment an action runs (two previews can each look fine while only one fits), and an append-only **audit log** (`audit.jsonl`) that records proposals, executions and refusals, storing params as a digest only.

## Operations

| operation | gated | what it does |
|---|---|---|
| `notes.list`, `notes.read` | no | read the tenant's notes by exact path |
| `notes.publish` | yes | copy a note to the tenant's `published/` folder |
| `spend.balance` | no | cap, spent and remaining |
| `spend.charge` | yes | record a spend against the cap |

## Run it

```bash
uv sync
uv run pytest                      # 33 tests: gate, tenant scoping, budget, audit
cp -r fixtures data                # two demo tenants: acme, globex
claude mcp add approval-gate -e GATE_TENANT=acme -e GATE_DATA_DIR=$PWD/data -- \
  uv run --directory $PWD python -m approval_gate_mcp
```

Ask Claude Code to charge 12.00 to the budget. It shows the preview and a token. Confirming fails until you approve in another terminal:

```bash
GATE_TENANT=acme GATE_DATA_DIR=$PWD/data uv run python -m approval_gate_mcp.approve <token>
```

`uv run python scripts/smoke.py` runs the whole flow over real MCP stdio.

## What the tests pin down

- The model cannot approve its own action; an approval for different params does not unlock a proposal; approvals are consumed with the token.
- Nothing runs on the first call; the confirmed action is the proposed one even if different params are resent.
- Tokens are single use, expire, and cannot cross operations or tenants (including through a shared gate).
- Over-cap spends are refused, including when both previews were fine and the cap is hit between them.
- `../` traversal, absolute paths, `~`, symlink escapes and credential-named files are all refused.
- No operation exposes a tenant argument; there is no search operation.

## Provenance

This is a generic version of the design behind a private server I run for my own studio (WhatsApp and a read-only vault behind the same gate, plus an OAuth 2.1 login for claude.ai's hosted connector). I build with Claude Code agents and review, test and own what ships; the tests above are how I check the agents' work.

## Limits, stated plainly

- Approval files live on disk. In a real deployment the approver is a separate service (a one-tap approval in Slack or a web page, tied to a user identity), and the agent runtime must not be able to write the approvals folder (a Claude Code `PreToolUse` hook that denies it, or a separate container).
- Pending tokens are in memory on purpose: a restart forces a fresh preview.
- Single tenant per server process. A multi-tenant gateway would stamp the tenant from the authenticated session instead of the environment.

## Not in this repo

Hosted HTTP transport and OAuth (the private server has them), real connectors, a database.
