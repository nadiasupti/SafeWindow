"""The daily GitHub Actions check must stay a check: it records, it never alerts or rebuilds data."""
from pathlib import Path

import yaml

FLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "daily-check.yml"


def flow() -> dict:
    return yaml.safe_load(FLOW.read_text(encoding="utf-8"))


def test_runs_every_morning_and_by_hand():
    on = flow()[True]                                   # YAML 1.1 reads the key "on" as True
    assert on["schedule"] == [{"cron": "0 0 * * *"}] and "workflow_dispatch" in on


def test_only_checks_and_saves_the_result():
    text = FLOW.read_text(encoding="utf-8")
    assert "python scripts/daily_check.py" in text and "git add data/monitor" in text
    for forbidden in ("send_alert", "admin_app", "firebase deploy", "pipeline/", "build_pwa"):
        assert forbidden not in text, forbidden


def test_key_comes_from_a_secret_and_is_never_printed():
    text = FLOW.read_text(encoding="utf-8")
    assert "${{ secrets.EE_SERVICE_ACCOUNT_KEY_JSON }}" in text
    assert "$RUNNER_TEMP/ee-key.json" in text            # a temporary file, gone with the runner
    assert "cat " not in text and "echo \"$EE_KEY_JSON" not in text
    assert flow()["permissions"] == {"contents": "write"}
