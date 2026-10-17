import json

import pytest

from approval_gate_mcp.errors import GateError


def charge(d, cents, memo="m"):
    token = json.loads(d.execute("spend.charge", {"amount_cents": cents, "memo": memo}))["confirm_token"]
    return d.execute("spend.charge", {"confirm_token": token})


def test_cap_is_enforced(acme):
    charge(acme, 30_000)
    with pytest.raises(GateError, match="over budget"):
        charge(acme, 30_000)
    assert json.loads(acme.execute("spend.balance", {}))["remaining_cents"] == 20_000


def test_cap_is_rechecked_when_the_action_runs(acme):
    t1 = json.loads(acme.execute("spend.charge", {"amount_cents": 40_000, "memo": "a"}))["confirm_token"]
    t2 = json.loads(acme.execute("spend.charge", {"amount_cents": 40_000, "memo": "b"}))["confirm_token"]
    acme.execute("spend.charge", {"confirm_token": t1})
    with pytest.raises(GateError, match="over budget"):  # both previews looked fine; only one fits
        acme.execute("spend.charge", {"confirm_token": t2})


def test_non_positive_amounts_are_refused(acme):
    for bad in (0, -5):
        token = json.loads(acme.execute("spend.charge", {"amount_cents": bad, "memo": "m"}))["confirm_token"]
        with pytest.raises(GateError, match="greater than 0"):
            acme.execute("spend.charge", {"confirm_token": token})


def test_publish_goes_through_the_gate(acme):
    out = json.loads(acme.execute("notes.publish", {"path": "q3-plan.md"}))
    assert out["pending"] and not (acme.tenant.root / "published").exists()
    acme.execute("notes.publish", {"confirm_token": out["confirm_token"]})
    assert (acme.tenant.root / "published" / "q3-plan.md").is_file()


def test_audit_log_records_proposals_executions_and_refusals(acme):
    token = json.loads(acme.execute("spend.charge", {"amount_cents": 100, "memo": "m"}))["confirm_token"]
    acme.execute("spend.charge", {"confirm_token": token})
    with pytest.raises(GateError):
        acme.execute("spend.charge", {"confirm_token": token})
    lines = [json.loads(x) for x in (acme.tenant.root / "audit.jsonl").read_text().splitlines()]
    assert [l["outcome"] for l in lines] == ["proposed", "executed", "refused"]
    assert all("memo" not in json.dumps(l) for l in lines)  # params are stored as a digest only
