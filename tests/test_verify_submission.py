"""Tests for the independent-review rule in the submission evidence gate."""

from scripts.verify_submission import review_errors

FILLED = {"name": "A. Reviewer", "affiliation": "University", "contact": "a@b.org", "date": "2026-10-20",
          "decision": "approved with changes", "summary": "Re-ran the checks; results reproduce."}


def test_filled_and_approved_review_passes():
    assert review_errors(FILLED) == []


def test_unfilled_template_is_rejected():
    template = dict.fromkeys(FILLED, "") | {"decision": "approved / approved with changes / not approved"}
    errors = review_errors(template)
    assert errors and "missing" in errors[0]


def test_review_that_does_not_approve_is_rejected():
    assert review_errors(FILLED | {"decision": "not approved"})
    assert review_errors(FILLED | {"decision": "approved / approved with changes / not approved"})
