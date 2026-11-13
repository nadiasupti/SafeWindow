"""Action tools built on the isolation timeline: an aid dispatch plan, a people-cut-off curve
and a rainfall watch.

All numbers here are planning assumptions, not measurements. They are named constants so a
user can change them, and every output says so. The rainfall watch is a rule of thumb from
a rank correlation over few dates (see results/rain_flood_lag.csv); it is not a forecast.
"""
from __future__ import annotations

import math

import pandas as pd

HOUSEHOLD_SIZE = 5                  # people per household (assumption)
BOAT_HOUSEHOLDS = 40                # households one relief boat trip can supply (assumption)
SOON_DAYS = 3                       # "due soon" window before the aid deadline
RAIN_WINDOW_DAYS = 10               # rolling rainfall window
RAIN_LAG_DAYS = 6                   # days from heavy rain to first cut roads in the 2022 data


def dispatch_plan(villages: pd.DataFrame, today, household_size: int = HOUSEHOLD_SIZE,
                  boat_households: int = BOAT_HOUSEHOLDS) -> pd.DataFrame:
    """One row per isolated village, most urgent first.

    `villages` needs name, population, outcome, urgency_rank and aid_deadline.
    `days_left` is the aid deadline minus `today` (negative = overdue).
    """
    today = pd.Timestamp(today).normalize()
    iso = villages[villages["outcome"] == "isolated"].copy()
    if iso.empty:
        return pd.DataFrame(columns=["rank", "village", "population", "households", "boat_trips",
                                     "aid_deadline", "days_left", "priority"])
    pop = iso["population"].fillna(0)
    iso["households"] = (pop / household_size).apply(math.ceil)
    iso["boat_trips"] = (iso["households"] / boat_households).apply(math.ceil)
    iso["days_left"] = (pd.to_datetime(iso["aid_deadline"]) - today).dt.days
    iso["priority"] = iso["days_left"].apply(
        lambda d: "unknown" if pd.isna(d) else "overdue" if d < 0 else "due soon" if d <= SOON_DAYS else "later")
    out = iso.rename(columns={"urgency_rank": "rank", "name": "village"})
    return out.sort_values(["rank", "village"], na_position="last")[
        ["rank", "village", "population", "households", "boat_trips", "aid_deadline", "days_left", "priority"]
    ].reset_index(drop=True)


def dispatch_waves(plan: pd.DataFrame) -> pd.DataFrame:
    """Plan grouped by aid-deadline date: how many villages, households and boat trips per day."""
    if plan.empty:
        return pd.DataFrame(columns=["aid_deadline", "villages", "households", "boat_trips"])
    return (plan.groupby("aid_deadline", dropna=False)
            .agg(villages=("village", "count"), households=("households", "sum"), boat_trips=("boat_trips", "sum"))
            .reset_index().sort_values("aid_deadline"))


def dispatch_csv(plan: pd.DataFrame) -> str:
    """The plan as BOM-prefixed CSV with ISO dates, matching the responder CSV."""
    out = plan.copy()
    out["aid_deadline"] = pd.to_datetime(out["aid_deadline"]).dt.strftime("%Y-%m-%d").fillna("")
    return chr(0xFEFF) + out.to_csv(index=False)


def people_cut_off(villages: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    """Catchment population of villages classed isolated on each observation date."""
    pop = villages.set_index("village_id")["population"].fillna(0)
    iso = status[status["status"] == "isolated"].copy()
    iso["population"] = iso["village_id"].map(pop).fillna(0)
    by_day = iso.groupby("date").agg(villages=("village_id", "nunique"), people=("population", "sum"))
    dates = pd.Index(sorted(status["date"].unique()), name="date")
    return by_day.reindex(dates, fill_value=0).reset_index()


def story_moments(curve: pd.DataFrame) -> list[tuple[str, str]]:
    """Plain-language headline moments from the people-cut-off curve: first cut, peak, last cut."""
    hit = curve[curve["people"] > 0]
    if hit.empty:
        return [("No isolation", "No village was classed as isolated on any observation date.")]
    peak = hit.loc[hit["people"].idxmax()]
    fmt = lambda d: pd.Timestamp(d).strftime("%d %b %Y")
    return [("First village cut off", f"{fmt(hit['date'].iloc[0])}: {int(hit['villages'].iloc[0])} village(s), "
                                     f"{int(hit['people'].iloc[0]):,} people."),
            ("Peak isolation", f"{fmt(peak['date'])}: {int(peak['villages'])} village(s), {int(peak['people']):,} people."),
            ("Last observed cut", f"{fmt(hit['date'].iloc[-1])}: {int(hit['villages'].iloc[-1])} village(s).")]


def rain_watch(rain: pd.DataFrame, column: str, window_days: int = RAIN_WINDOW_DAYS,
               lag_days: int = RAIN_LAG_DAYS) -> pd.DataFrame:
    """Rolling rainfall and a rule-of-thumb watch level.

    level: 'warning' when the window total is at least 75% of the highest window in the record,
    'watch' at 50%, otherwise 'normal'. `cut_expected` is the date + lag_days at which roads
    started to be cut in the studied flood. Not a forecast: few dates, one region.
    """
    r = rain[["date", column]].copy()
    r["date"] = pd.to_datetime(r["date"])
    r = r.sort_values("date")
    r["window_mm"] = r[column].rolling(window_days, min_periods=1).sum()
    top = r["window_mm"].max()
    share = r["window_mm"] / top if top > 0 else r["window_mm"] * 0
    r["level"] = share.apply(lambda s: "warning" if s >= 0.75 else "watch" if s >= 0.5 else "normal")
    r["cut_expected"] = r["date"] + pd.Timedelta(days=lag_days)
    return r.rename(columns={column: "daily_mm"}).reset_index(drop=True)
