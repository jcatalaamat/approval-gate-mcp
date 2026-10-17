import json

import pytest

from approval_gate_mcp.errors import GateError
from approval_gate_mcp.gate import ApprovalGate


def propose(d, op="spend.charge", **params):
    params = params or {"amount_cents": 1200, "memo": "api credits"}
    return json.loads(d.execute(op, params))


def test_first_call_only_previews_and_does_nothing(acme):
    out = propose(acme)
    assert out["pending"] is True and out["confirm_token"]
    assert json.loads(acme.execute("spend.balance", {}))["spent_cents"] == 0


def test_confirm_runs_the_action(acme):
    token = propose(acme)["confirm_token"]
    out = json.loads(acme.execute("spend.charge", {"confirm_token": token}))
    assert out["charged_cents"] == 1200 and out["remaining_cents"] == 50000 - 1200


def test_confirm_runs_the_proposed_params_not_the_resent_ones(acme):
    token = propose(acme)["confirm_token"]
    out = json.loads(acme.execute("spend.charge", {"confirm_token": token, "amount_cents": 49_000, "memo": "swapped"}))
    assert out["charged_cents"] == 1200


def test_token_is_single_use(acme):
    token = propose(acme)["confirm_token"]
    acme.execute("spend.charge", {"confirm_token": token})
    with pytest.raises(GateError, match="invalid or expired"):
        acme.execute("spend.charge", {"confirm_token": token})


def test_token_expires(acme, clock):
    token = propose(acme)["confirm_token"]
    clock.now += 601
    with pytest.raises(GateError, match="invalid or expired|expired"):
        acme.execute("spend.charge", {"confirm_token": token})
    assert json.loads(acme.execute("spend.balance", {}))["spent_cents"] == 0


def test_token_from_one_operation_cannot_confirm_another(acme):
    token = propose(acme)["confirm_token"]
    with pytest.raises(GateError, match="does not belong"):
        acme.execute("notes.publish", {"confirm_token": token})


def test_wrong_context_attempt_does_not_burn_the_real_token(acme):
    token = propose(acme)["confirm_token"]
    with pytest.raises(GateError):
        acme.execute("notes.publish", {"confirm_token": token})
    assert json.loads(acme.execute("spend.charge", {"confirm_token": token}))["charged_cents"] == 1200


def test_token_cannot_cross_tenants(make, clock):
    gate = ApprovalGate(clock=clock)  # one shared gate, two tenants: the binding must hold
    acme, globex = make("acme", gate), make("globex", gate)
    token = json.loads(acme.execute("spend.charge", {"amount_cents": 100, "memo": "x"}))["confirm_token"]
    with pytest.raises(GateError, match="does not belong"):
        globex.execute("spend.charge", {"confirm_token": token})
    assert json.loads(globex.execute("spend.balance", {}))["spent_cents"] == 0


def test_unknown_token_is_refused(acme):
    with pytest.raises(GateError, match="invalid or expired"):
        acme.execute("spend.charge", {"confirm_token": "nope"})


def test_invalid_params_are_refused_before_a_token_is_minted(acme):
    with pytest.raises(GateError, match="missing required"):
        acme.execute("spend.charge", {"amount_cents": 100})
    with pytest.raises(GateError, match="must be an integer"):
        acme.execute("spend.charge", {"amount_cents": "100", "memo": "x"})
    assert not acme.gate._pending


def test_expired_tokens_are_swept(acme, clock):
    propose(acme)
    clock.now += 700
    propose(acme)
    assert len(acme.gate._pending) == 1
