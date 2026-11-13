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


WATCH = FLOW.parent / "watch.yml"


def test_the_watch_runs_only_when_started_by_hand():
    flow = yaml.safe_load(WATCH.read_text(encoding="utf-8"))
    assert flow[True] == {"workflow_dispatch": {}}                     # no schedule: the admin switched it off
    assert flow["permissions"] == {"contents": "read"}                 # it saves nothing in the repository


def test_the_watch_only_makes_pending_alerts_and_keeps_its_keys_secret():
    text = WATCH.read_text(encoding="utf-8")
    assert "python scripts/watch.py" in text and "--drafts" in text and "--data-url" in text
    for forbidden in ("send_alert", "admin_app", "SAFEWINDOW_ALLOW_LIVE", "SAFEWINDOW_ALLOW_UNVALIDATED_FORECAST",
                      "firebase deploy", "git push"):
        assert forbidden not in text, forbidden
    assert "${{ secrets.FIREBASE_ADMIN_KEY_JSON }}" in text and "${{ secrets.GEMINI_API_KEY }}" in text
    assert "$RUNNER_TEMP/firebase-key.json" in text
    assert "cat " not in text and "echo \"$FIREBASE_KEY_JSON" not in text
