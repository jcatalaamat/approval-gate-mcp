import json

import pytest

from approval_gate_mcp.errors import GateError
from approval_gate_mcp.tenant import Tenant


def test_reads_only_this_tenants_notes(make):
    acme, globex = make("acme"), make("globex")
    assert "Acme-only" in acme.execute("notes.read", {"path": "welcome.md"})
    assert "Globex-only" in globex.execute("notes.read", {"path": "welcome.md"})
    with pytest.raises(GateError):
        globex.execute("notes.read", {"path": "q3-plan.md"})  # exists for acme, not for globex


@pytest.mark.parametrize("bad", ["../globex/notes/welcome.md", "../../acme/budget.json", "/etc/passwd", "~/x", "a/../../b"])
def test_path_traversal_is_refused(acme, bad):
    with pytest.raises(GateError):
        acme.execute("notes.read", {"path": bad})


def test_symlink_escape_is_refused(acme, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("secret")
    (acme.tenant.notes_root / "link.md").symlink_to(outside)
    with pytest.raises(GateError, match="escapes"):
        acme.execute("notes.read", {"path": "link.md"})


def test_credential_files_are_unreadable_and_unlisted(acme):
    with pytest.raises(GateError, match="denylist"):
        acme.execute("notes.read", {"path": "credentials-prod.md"})
    names = [r["name"] for r in json.loads(acme.execute("notes.list", {}))]
    assert "welcome.md" in names and "credentials-prod.md" not in names


def test_there_is_no_search_operation(acme):
    assert not [op for op in acme.flat if "search" in op]


def test_tenant_must_exist_and_be_well_formed(data_dir):
    for bad in ["", "../acme", "ACME", "nope"]:
        with pytest.raises(GateError):
            Tenant.create(bad, data_dir)


def test_tools_expose_no_tenant_argument(acme):
    for op in acme.flat.values():
        assert "tenant" not in op["inputSchema"]["properties"]
