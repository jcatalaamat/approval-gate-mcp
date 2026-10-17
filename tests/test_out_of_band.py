import json

import pytest

from approval_gate_mcp import approve
from approval_gate_mcp.dispatch import Dispatcher
from approval_gate_mcp.errors import GateError
from approval_gate_mcp.gate import ApprovalGate, digest
from approval_gate_mcp.tenant import Tenant


@pytest.fixture
def strict(data_dir, clock):
    return Dispatcher(Tenant.create("acme", data_dir), ApprovalGate(clock=clock), require_approval=True)


def preview(d, cents=1200):
    return json.loads(d.execute("spend.charge", {"amount_cents": cents, "memo": "m"}))


def human_approves(monkeypatch, d, token):
    monkeypatch.setenv("GATE_TENANT", d.tenant.id)
    monkeypatch.setenv("GATE_DATA_DIR", str(d.tenant.root.parent))
    monkeypatch.setattr("builtins.input", lambda _="": "y")
    assert approve.main([token]) == 0


def test_model_cannot_approve_its_own_action(strict):
    token = preview(strict)["confirm_token"]
    with pytest.raises(GateError, match="awaiting human approval"):
        strict.execute("spend.charge", {"confirm_token": token})
    assert json.loads(strict.execute("spend.balance", {}))["spent_cents"] == 0


def test_human_approval_unlocks_exactly_that_action(strict, monkeypatch):
    token = preview(strict)["confirm_token"]
    human_approves(monkeypatch, strict, token)
    out = json.loads(strict.execute("spend.charge", {"confirm_token": token, "amount_cents": 49_000}))
    assert out["charged_cents"] == 1200  # resent params ignored, proposed ones run


def test_approval_is_consumed_with_the_token(strict, monkeypatch):
    token = preview(strict)["confirm_token"]
    human_approves(monkeypatch, strict, token)
    strict.execute("spend.charge", {"confirm_token": token})
    with pytest.raises(GateError):
        strict.execute("spend.charge", {"confirm_token": token})
    assert not list(strict.tenant.approvals_dir.glob(f"{token}*"))


def test_declined_approval_stays_locked(strict, monkeypatch):
    token = preview(strict)["confirm_token"]
    monkeypatch.setenv("GATE_TENANT", "acme")
    monkeypatch.setenv("GATE_DATA_DIR", str(strict.tenant.root.parent))
    monkeypatch.setattr("builtins.input", lambda _="": "n")
    assert approve.main([token]) == 1
    with pytest.raises(GateError, match="awaiting human approval"):
        strict.execute("spend.charge", {"confirm_token": token})


def test_approval_for_other_params_does_not_unlock(strict):
    token = preview(strict, 1200)["confirm_token"]
    # a grant whose digest was computed over different params must not unlock the proposal
    strict.tenant.grant(token, digest("acme", "spend.charge", {"amount_cents": 1, "memo": "m"}))
    with pytest.raises(GateError, match="does not match"):
        strict.execute("spend.charge", {"confirm_token": token})


def test_token_names_cannot_escape_the_approvals_folder(strict):
    for bad in ["../x", "a/b", "short", "x" * 70, ""]:
        with pytest.raises(GateError):
            strict.tenant.granted_digest(bad)
