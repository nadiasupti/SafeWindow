"""scripts/provision_government.py: the only way to create a government account."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import provision_government as pg  # noqa: E402


def test_grant_sets_only_the_gov_role_and_keeps_other_claims():
    assert pg.claims_after(None, grant=True) == {"role": "gov"}
    assert pg.claims_after({"beta": True}, grant=True) == {"beta": True, "role": "gov"}


def test_revoke_removes_the_role_and_keeps_other_claims():
    assert pg.claims_after({"role": "gov", "beta": True}, grant=False) == {"beta": True}
    assert pg.claims_after({}, grant=False) == {}


def test_the_role_name_is_the_one_the_rules_check():
    rules = (ROOT / "firestore.rules").read_text(encoding="utf-8")
    assert f"request.auth.token.get('role', '') == '{pg.ROLE}'" in rules


def test_it_refuses_to_run_without_the_admin_key(monkeypatch, capsys):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert pg.main(["someone@example.org"]) == 2
    assert "Admin key" in capsys.readouterr().err
