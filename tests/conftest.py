import shutil
from pathlib import Path

import pytest

from approval_gate_mcp.dispatch import Dispatcher
from approval_gate_mcp.gate import ApprovalGate
from approval_gate_mcp.tenant import Tenant

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def data_dir(tmp_path):
    shutil.copytree(FIXTURES, tmp_path / "data")
    return tmp_path / "data"


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def make(data_dir, clock):
    def _make(tenant_id="acme", gate=None):
        return Dispatcher(Tenant.create(tenant_id, data_dir), gate or ApprovalGate(clock=clock))

    return _make


@pytest.fixture
def acme(make):
    return make("acme")
