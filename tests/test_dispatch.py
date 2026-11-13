import pandas as pd

from safewindow import dispatch


def villages():
    return pd.DataFrame({
        "village_id": ["a", "b", "c"], "name": ["A", "B", "C"], "population": [1000, 205, None],
        "outcome": ["isolated", "isolated", "connected_when_seen"], "urgency_rank": [1, 2, None],
        "aid_deadline": pd.to_datetime(["2022-05-23", "2022-06-10", None])})


def test_plan_counts_households_and_boats():
    plan = dispatch.dispatch_plan(villages(), "2022-05-25")
    assert list(plan["village"]) == ["A", "B"]
    assert list(plan["households"]) == [200, 41]
    assert list(plan["boat_trips"]) == [5, 2]
    assert list(plan["priority"]) == ["overdue", "later"]
    assert plan["days_left"].iloc[0] == -2


def test_plan_empty_and_waves():
    empty = dispatch.dispatch_plan(villages().assign(outcome="connected_when_seen"), "2022-05-25")
    assert empty.empty and dispatch.dispatch_waves(empty).empty
    waves = dispatch.dispatch_waves(dispatch.dispatch_plan(villages(), "2022-05-25"))
    assert list(waves["villages"]) == [1, 1] and waves["households"].sum() == 241


def test_csv_has_bom_and_iso_dates():
    csv = dispatch.dispatch_csv(dispatch.dispatch_plan(villages(), "2022-05-25"))
    assert csv.startswith("﻿") and "2022-05-23" in csv


def test_people_cut_off_and_story():
    status = pd.DataFrame({"date": pd.to_datetime(["2022-05-16", "2022-05-16", "2022-05-23", "2022-05-23"]),
                           "village_id": ["a", "b", "a", "b"],
                           "status": ["connected", "isolated", "isolated", "isolated"]})
    curve = dispatch.people_cut_off(villages(), status)
    assert list(curve["people"]) == [205, 1205]
    moments = dict(dispatch.story_moments(curve))
    assert "23 May 2022" in moments["Peak isolation"] and "1,205" in moments["Peak isolation"]
    assert dispatch.story_moments(curve.assign(people=0))[0][0] == "No isolation"


def test_rain_watch_levels_and_lag():
    rain = pd.DataFrame({"date": pd.date_range("2022-05-20", periods=4), "mm": [0, 10, 40, 0]})
    w = dispatch.rain_watch(rain, "mm", window_days=2, lag_days=6)
    assert list(w["level"]) == ["normal", "normal", "warning", "warning"]
    assert w["cut_expected"].iloc[0] == pd.Timestamp("2022-05-26")
