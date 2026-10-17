"""End-to-end check over real MCP stdio: spawn the server, discover, preview, confirm, and try to cross tenants."""
import asyncio, json, os, shutil, sys, tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


async def call(s, name, **args):
    r = await s.call_tool(name, args)
    return r.content[0].text


async def main():
    data = Path(tempfile.mkdtemp()) / "data"
    shutil.copytree(ROOT / "fixtures", data)
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "approval_gate_mcp"], cwd=str(ROOT),
        env={**os.environ, "GATE_TENANT": "acme", "GATE_DATA_DIR": str(data)},
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            print("tools:", tools)
            print("discover:", list(json.loads(await call(s, "discover")).keys()))
            prev = json.loads(await call(s, "execute", operation="spend.charge", params={"amount_cents": 1200, "memo": "api credits"}))
            print("preview pending:", prev["pending"], "| balance untouched:", json.loads(await call(s, "execute", operation="spend.balance"))["spent_cents"] == 0)
            done = json.loads(await call(s, "execute", operation="spend.charge", params={"confirm_token": prev["confirm_token"], "amount_cents": 49000}))
            print("confirmed, charged:", done["charged_cents"], "(resent 49000 ignored)")
            print("replay:", await call(s, "execute", operation="spend.charge", params={"confirm_token": prev["confirm_token"]}))
            print("traversal:", await call(s, "execute", operation="notes.read", params={"path": "../globex/notes/welcome.md"}))
            print("credentials:", await call(s, "execute", operation="notes.read", params={"path": "credentials-prod.md"}))
    print("audit:", [json.loads(l)["outcome"] for l in (data / "acme" / "audit.jsonl").read_text().splitlines()])


asyncio.run(main())
