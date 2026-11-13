"""SafeWindow admin panel: write, approve, send, cancel and log village alerts (app plan, step 3).

Runs only on the admin's own computer, where the Firebase Admin key is:

    $env:GOOGLE_APPLICATION_CREDENTIALS="E:\\keys\\safewindow-admin.json"
    python -m streamlit run app/admin_app.py --server.address 127.0.0.1 --server.port 8502

It is a separate app from the public one (app/streamlit_app.py) and is never deployed. It refuses to open from any
address but this computer, and without the Admin key. SIMULATION alerts reach registered test phones only; real
alerts stay switched off unless SAFEWINDOW_ALLOW_LIVE=1 is set. The panel speaks Bangla or English
(app/admin_text.py); the alert messages are always written in both.
"""
from __future__ import annotations

import os
import sys
from datetime import date as Date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from admin_text import LANGS, text  # noqa: E402

from safewindow import alerts, forecast, monitor, watch  # noqa: E402


def lang() -> str:
    return st.session_state.get("admin_lang", "bn")


def t(key: str, **kw) -> str:
    return text(lang(), key, **kw)


def guard() -> None:
    """Open only on this computer, and only with the Admin key."""
    host = (st.context.headers.get("Host") or "").split(":")[0]
    if host not in ("localhost", "127.0.0.1", "::1", "[::1]"):
        st.error("The admin panel opens only on the admin's own computer.")
        st.stop()
    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not key or not Path(key).is_file():
        st.error("Set GOOGLE_APPLICATION_CREDENTIALS to the Firebase Admin key file (kept outside the repository), "
                 "then start the panel again.")
        st.stop()


@st.cache_resource
def db():
    return alerts.firestore_client()


def flash(message: str, kind: str = "success") -> None:
    st.session_state["flash"] = (kind, message)


def show_flash() -> None:
    if "flash" in st.session_state:
        kind, message = st.session_state.pop("flash")
        getattr(st, kind)(message)


def preview(rec: dict) -> None:
    for code in ("bn", "en"):
        p = rec["preview"][code]
        st.markdown(f"**{p['title']}**  \n{p['body']}")


def village_picker(key: str, flood: str, default: str | None = None) -> dict:
    vs = sorted(alerts.villages(flood), key=lambda v: (v.get("urgency_rank") or 999, v["name"]))
    ids = [v["id"] for v in vs]
    index = ids.index(default) if default in ids else 0
    return vs[st.selectbox(t("village"), range(len(vs)), index=index, key=key,
                           format_func=lambda i: f"{alerts.village_name(vs[i], lang())} · {t('outcome_' + vs[i]['outcome'])}")]


def flood_picker(key: str) -> str:
    fl = alerts.floods()
    return fl[st.selectbox(t("flood"), range(len(fl)), key=key, format_func=lambda i: fl[i]["name"])]["id"]


def tab_new(admin: str) -> None:
    flood = flood_picker("new_flood")
    v = village_picker("new_village", flood)
    status = alerts.flood_status(flood)
    level = st.radio(t("level"), alerts.LEVELS, format_func=lambda x: t("level_" + x), horizontal=True, key="new_level")
    reason = st.selectbox(t("reason"), alerts.REASONS, format_func=lambda x: t("reason_" + x), key="new_reason")
    date, texts = None, None
    if reason in ("roads", "isolated"):
        date = st.selectbox(t("radar_date"), status["dates"][::-1], key="new_date")
    elif reason == "rain":
        date = st.date_input(t("rain_date"), value=Date.fromisoformat(status["dates"][-1]), key="new_rain").isoformat()
    else:
        texts = {"bn": st.text_area(t("official_bn"), key="new_bn"), "en": st.text_area(t("official_en"), key="new_en")}
    hours = st.slider(t("hours"), 1, alerts.MAX_HOURS, 24, key="new_hours")
    live = alerts.live_allowed()
    simulation = st.checkbox(t("simulation"), value=True, disabled=not live, key="new_sim",
                             help=None if live else t("live_help"))
    try:
        rec = alerts.new_alert(flood, v["id"], level, reason, admin, date=date, texts=texts, hours=hours,
                               simulation=simulation)
    except (ValueError, KeyError) as exc:
        st.warning(str(exc))
        return
    st.markdown(f"##### {t('preview')}")
    preview(rec)
    c1, c2 = st.columns(2)
    if c1.button(t("save_draft"), key="new_save"):
        alerts.save(db(), rec)
        flash(t("saved_draft"))
        st.rerun()
    if c2.button(t("submit"), type="primary", key="new_submit"):
        alerts.save(db(), alerts.submit(rec, admin))
        flash(t("submitted"))
        st.rerun()


def not_a_repeat(rec: dict, key: str) -> bool:
    """False while the same alert was sent in the last few minutes, unless the admin ticks 'send anyway'.
    Reads the log afresh, so a double click finds the first send."""
    dup = alerts.recent_duplicate(rec, alerts.load_alerts(db()))
    if not dup:
        return True
    st.warning(t("duplicate", at=dup["published_at"], m=alerts.DUPLICATE_MINUTES))
    return st.checkbox(t("send_anyway"), key=key)


def tab_approve(admin: str, all_alerts: list[dict]) -> None:
    waiting = [r for r in all_alerts if r["status"] in ("pending", "draft")]
    if not waiting:
        st.info(t("nothing_waiting"))
        return
    subs, test_ids = alerts.load_subscriptions(db()), alerts.load_test_ids(db())
    for rec in waiting:
        with st.container(border=True):
            st.markdown(f"{t('status_' + rec['status'])} · {t('level_' + rec['level'])} · **{rec['village_name']}** · "
                        f"{'SIMULATION' if rec['simulation'] else t('real')} · {t('written_by', name=rec['created_by'])}")
            preview(rec)
            chosen = alerts.recipients(subs, rec["flood"], rec["village"], test_ids if rec["simulation"] else None)
            st.caption(t("goes_to", n=len(chosen), who=t("test_phones") if rec["simulation"] else t("all_subscribers")))
            if rec["status"] == "draft":
                if st.button(t("submit"), key=f"sub_{rec['id']}"):
                    alerts.save(db(), alerts.submit(rec, admin))
                    st.rerun()
                continue
            verified = st.checkbox(t("verified"), key=f"ver_{rec['id']}")
            again = not_a_repeat(rec, f"rep_{rec['id']}")
            c1, c2 = st.columns(2)
            if c1.button(t("publish"), type="primary", key=f"pub_{rec['id']}", disabled=not (verified and again)):
                try:
                    alerts.save(db(), alerts.publish(rec, admin, subs, test_ids, alerts.fcm_sender(db()), verified))
                    flash(t("sent", sent=rec["sent"], failed=rec["failed"]))
                except ValueError as exc:
                    flash(str(exc), "error")
                st.rerun()
            note = c2.text_input(t("reject_reason"), key=f"rejnote_{rec['id']}")
            if c2.button(t("reject"), key=f"rej_{rec['id']}"):
                try:
                    alerts.save(db(), alerts.reject(rec, admin, note))
                    flash(t("rejected"), "info")
                except ValueError as exc:
                    flash(str(exc), "error")
                st.rerun()


def tab_log(admin: str, all_alerts: list[dict]) -> None:
    if not all_alerts:
        st.info(t("no_alerts"))
        return
    st.dataframe(pd.DataFrame([{
        t("col_created"): r["created_at"], t("col_status"): t("status_" + alerts.status_now(r)),
        t("col_level"): r["level"], t("col_village"): r["village_name"], "SIMULATION": r["simulation"],
        "Demo": r.get("demo", False), t("col_by"): r["created_by"], t("col_approved"): r.get("approved_by", ""),
        t("col_sent"): r.get("sent", ""), t("col_failed"): r.get("failed", ""), t("col_expires"): r.get("expires_at", ""),
    } for r in all_alerts]), hide_index=True, use_container_width=True)
    subs, test_ids = None, None
    for rec in all_alerts:
        state = alerts.status_now(rec)
        with st.expander(f"{t('status_' + state)} · {rec['village_name']} · {rec['created_at']}"):
            preview(rec)
            st.table(pd.DataFrame(rec.get("history", [])))
            if state in ("published", "expired"):
                note = st.text_input(t("cancel_reason"), key=f"cnote_{rec['id']}")
                if st.button(t("cancel"), key=f"can_{rec['id']}"):
                    if subs is None:
                        subs, test_ids = alerts.load_subscriptions(db()), alerts.load_test_ids(db())
                    try:
                        alerts.save(db(), alerts.cancel(rec, admin, note, subs, test_ids, alerts.fcm_sender(db())))
                        flash(t("cancelled"), "info")
                    except ValueError as exc:
                        flash(str(exc), "error")
                    st.rerun()


def suggestion(codes: str, dates: list[str], i: int, v: dict, supply_days: int = 7) -> tuple[str, str] | None:
    """Demo: the alert a replay proposes on radar date i, from what that date's radar showed only.
    Isolated: Warning; Critical once household supplies may run out within 2 days (the app's estimate).
    Connected or uncertain: nothing (no claim the data on that date cannot support)."""
    if i >= len(codes) or codes[i] != "i":
        return None
    start = v.get("isolated_from_earliest")
    if start:
        runs_out = (pd.Timestamp(start) + pd.Timedelta(days=supply_days)).date()
        if (runs_out - Date.fromisoformat(dates[i])).days <= 2:
            return "critical", "isolated"
    return "warning", "isolated"


def tab_demo(admin: str) -> None:
    st.caption(t("demo_help"))
    flood = flood_picker("demo_flood")
    v = village_picker("demo_village", flood, default="osm6123937356")
    status = alerts.flood_status(flood)
    dates, codes = status["dates"], status["villages"].get(v["id"], "")
    i = st.select_slider(t("demo_date"), options=range(len(dates)), format_func=lambda k: dates[k], key="demo_i")
    st.markdown(" ".join(f"{'**' if k == i else ''}{dates[k][5:]} {t('code_' + c).split()[0]}{'**' if k == i else ''}"
                         for k, c in enumerate(codes)))
    st.markdown(f"**{dates[i]}:** {t('code_' + codes[i]) if i < len(codes) else '?'}")
    s = suggestion(codes, dates, i, v)
    if not s:
        st.info(t("no_proposal"))
        return
    level, reason = s
    rec = alerts.new_alert(flood, v["id"], level, reason, admin, date=dates[i], hours=6, simulation=True, demo=True)
    st.markdown(f"##### {t('proposal')}")
    preview(rec)
    again = not_a_repeat(rec, "demo_repeat")
    if st.button(t("demo_send"), type="primary", key="demo_send", disabled=not again):
        subs, test_ids = alerts.load_subscriptions(db()), alerts.load_test_ids(db())
        alerts.submit(rec, admin)
        alerts.save(db(), alerts.publish(rec, admin, subs, test_ids, alerts.fcm_sender(db()), verified=True))
        flash(t("demo_sent", n=rec["sent"]))
        st.rerun()


@st.cache_resource
def forecast_model():
    """(model, test metrics). Loads data/forecast/model.json (scripts/train_forecast.py) or trains the demo model."""
    model = forecast.load_or_train()
    return model, model.meta.get("test_metrics") or forecast.train()[1]


def tab_forecast(admin: str, all_alerts: list[dict]) -> None:
    """AI early warning (DEMO, trained on synthetic data): estimate -> draft alerts -> the admin approves in the
    Approval tab -> the village's phones are notified by the same path as every other alert. Nothing is sent here."""
    st.caption(t("forecast_help"))
    model, metrics = forecast_model()
    flood = flood_picker("fc_flood")
    villages = alerts.villages(flood)

    found = {r["region"]: r for r in monitor.load_all() if forecast.rain_from_monitor(r)}
    options = ["scenario"] + (["monitor"] if found else [])
    source = st.radio(t("forecast_source"), options, horizontal=True, key="fc_source",
                      format_func=lambda x: t("src_scenario") if x == "scenario" else t("src_monitor"))
    if not found:
        st.caption(t("src_monitor_none"))
    if source == "monitor":
        region = st.selectbox("region", list(found), key="fc_region", format_func=lambda k: found[k]["name"])
        base, issue_date, label = forecast.rain_from_monitor(found[region]), found[region]["rain"][next(iter(found[region]["rain"]))]["through"], f"daily check: {region}"
    else:
        name = st.selectbox(t("scenario"), list(forecast.SCENARIOS), key="fc_scenario", format_func=lambda k: t("scenario_" + k))
        base, issue_date, label = forecast.SCENARIOS[name], pd.Timestamp.now(tz="UTC").date().isoformat(), f"demo scenario: {name}"
    st.markdown(f"**{t('rain_inputs')}**")
    cols = st.columns(len(forecast.RAIN_COLS))
    rain = {c: cols[i].slider(t(c), 0.0, 400.0, float(min(base[c], 400.0)), 1.0, key=f"fc_{source}_{label}_{c}")
            for i, c in enumerate(forecast.RAIN_COLS)}

    table = forecast.forecast_villages(model, villages, rain)
    shown = pd.DataFrame({
        t("col_village"): table["name"],
        t("col_prob"): (table["probability"] * 100).round().astype(int).astype(str) + "%",
        t("col_level"): table["level"].map(lambda x: t("level_" + x) if x != "none" else "—"),
        t("col_why"): table["why"].map(lambda w: ", ".join(t("why_" + k) for k in w)),
    })
    st.dataframe(shown, hide_index=True, use_container_width=True)
    st.bar_chart(table.set_index("name")["probability"])

    flagged = table[table["level"] != "none"]
    if flagged.empty:
        st.info(t("forecast_none"))
    else:
        waiting = {(r["flood"], r["village"], r.get("date")) for r in all_alerts
                   if r.get("reason") == "forecast" and r["status"] in ("draft", "pending")}
        fresh = flagged[[(flood, v, issue_date) not in waiting for v in flagged["village"]]]
        names = dict(zip(flagged["village"], flagged["name"]))
        chosen = st.multiselect(t("forecast_pick"), list(fresh["village"]), default=list(fresh["village"]),
                                format_func=lambda v: names[v], key=f"fc_pick_{flood}_{label}")
        hours = st.slider(t("forecast_hours"), 6, alerts.MAX_HOURS, 24, key="fc_hours")
        simulation = True
        if alerts.forecast_live_allowed():
            simulation = st.checkbox(t("simulation"), value=True, key="fc_sim")
        else:
            st.caption(t("forecast_sim_only"))
        if st.button(t("forecast_make"), type="primary", key="fc_make", disabled=not chosen):
            try:
                drafts = forecast.draft_alerts(model, table, flood, rain, label, admin, issue_date=issue_date,
                                               simulation=simulation, hours=hours, villages=set(chosen))
                for rec in drafts:
                    alerts.save(db(), alerts.submit(rec, admin))
                flash(t("forecast_done", n=len(drafts)))
            except ValueError as exc:
                flash(str(exc), "error")
            st.rerun()
    with st.expander(t("model_card")):
        st.write(t("model_card_text", trained=model.meta.get("trained_on", "?"), auc=metrics.get("auc"),
                   wp=metrics.get("watch_precision"), rate=round(100 * metrics.get("base_rate", 0))))
        st.json({k: v for k, v in model.meta.items() if k != "test_metrics"})


def tab_watch(admin: str, all_alerts: list[dict]) -> None:
    """Automated watch: satellite water + river/rain APIs (+ optional AI). It makes DRAFT alerts only; the admin approves
    them in the Approval tab, and only then is that village notified."""
    st.caption(t("watch_help"))
    flood = flood_picker("w_flood")
    provider = watch.ai_provider()
    use_ai = st.checkbox(t("watch_use_ai"), value=bool(provider), disabled=not provider, key="w_ai")
    if not provider:
        st.caption(t("watch_no_ai"))
    replay = st.checkbox(t("watch_replay"), key="w_replay")
    as_of = None
    if replay:
        days = alerts.flood_status(flood)["dates"]
        as_of = Date.fromisoformat(st.select_slider(t("watch_replay_date"), options=days, value=days[-1], key="w_asof"))
    if st.button(t("watch_run"), type="primary", key="w_run"):
        with st.spinner(t("watch_running")):
            try:
                rep = watch.run(flood, as_of=as_of, use_ai=use_ai)
                watch.save_report(rep)
            except Exception as exc:  # noqa: BLE001 - say what is wrong instead of a stack trace
                flash(t("watch_failed", e=exc), "error")
        st.rerun()
    report = watch.load_report(flood)
    if not report or not report.get("ok"):
        st.info(t("watch_no_report") if not report else report.get("why", ""))
        return
    st.markdown(t("watch_when", t=report["generated_at"][:16].replace("T", " "), mode=report["mode"]))
    rows = []
    for r in sorted(report["villages"], key=lambda r: -watch.LEVEL_NUM[r["level"]]):
        rows.append({t("col_village"): r["name"], t("col_level"): t("level_" + r["level"]) if r["level"] != "none" else "—",
                     **{t("sig_" + k): v for k, v in r["votes"].items()},
                     t("col_why"): r.get("ai_reason") or ""})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    flow = report.get("flow") or {}
    if flow.get("ok"):
        with st.expander(t("flow_title")):
            st.table(pd.DataFrame([{t("flow_col_day"): f"+{h}", t("flow_col_q"): f"{flow['predicted_m3s'][h]:.0f}",
                                    t("flow_col_level"): flow["levels"][h] if flow["levels"][h] != "none" else "—",
                                    t("flow_col_votes"): t("flow_yes") if int(h) in flow["voting_horizons"] else t("flow_no")}
                                   for h in ("1", "3", "7")]))
            st.caption(t("flow_note", now=f"{flow['today_m3s']:.0f}", w=f"{flow['thresholds_m3s']['watch']:.0f}"))
    if report["ai"].get("ok"):
        with st.expander(t("watch_ai_says", c=report["ai"].get("confidence"))):
            st.write(report["ai"].get("summary", ""))
            st.caption(report["ai"].get("limits", ""))
    try:
        png, _ = watch.render_image(flood, alerts.villages(flood), up_to=report["issue_date"])
        st.image(png)
    except Exception:  # noqa: BLE001 - the picture is a convenience
        pass
    flagged = [r for r in report["villages"] if r["level"] != "none"]
    if not flagged:
        st.info(t("watch_none"))
        return
    waiting = {(a["flood"], a["village"], a.get("date")) for a in all_alerts
               if a.get("reason") == "ai_watch" and a["status"] in ("draft", "pending")}
    fresh = [r for r in flagged if (flood, r["village"], report["issue_date"]) not in waiting]
    names = {r["village"]: r["name"] for r in flagged}
    chosen = st.multiselect(t("forecast_pick"), [r["village"] for r in fresh], default=[r["village"] for r in fresh],
                            format_func=lambda v: names[v], key=f"w_pick_{flood}_{report['generated_at']}")
    hours = st.slider(t("forecast_hours"), 6, alerts.MAX_HOURS, 24, key="w_hours")
    simulation = True
    if alerts.forecast_live_allowed():
        simulation = st.checkbox(t("simulation"), value=True, key="w_sim")
    else:
        st.caption(t("forecast_sim_only"))
    if st.button(t("watch_make"), type="primary", key="w_make", disabled=not chosen):
        try:
            drafts = watch.draft_alerts(report, admin, simulation=simulation, hours=hours, villages=set(chosen))
            for rec in drafts:
                alerts.save(db(), alerts.submit(rec, admin))
            flash(t("watch_done", n=len(drafts)))
        except ValueError as exc:
            flash(str(exc), "error")
        st.rerun()


def tab_monitor() -> None:
    """The daily check's latest findings (scripts/daily_check.py). Information only: nothing is sent from here."""
    st.caption(t("monitor_help"))
    found = monitor.load_all()
    for r in found:
        with st.container(border=True):
            st.markdown(f"**{r['name']}**")
            c1, c2, c3 = st.columns(3)
            c1.metric(t("newest_radar"), r["newest_radar"] or t("none"))
            c2.metric(t("new_images"), " ".join(r["new_since_last_check"]) or t("none"))
            c3.metric(t("checked_at"), r["checked_at"][:16].replace("T", " "))
            st.table(pd.DataFrame([
                {t("rain_box"): box, **{t("days_mm", w=w): "n/a" if v[f"{w}d_mm"] is None else f"{v[f'{w}d_mm']:.1f}"
                                         for w in monitor.RAIN_WINDOWS}, t("last_day"): v["through"]}
                for box, v in r["rain"].items()]))
    if found:
        st.caption(t("rain_note"))
    else:
        st.info(t("no_check"))
    if os.environ.get("EE_SERVICE_ACCOUNT_KEY") or os.environ.get("EE_PROJECT"):
        if st.button(t("check_now")):
            from safewindow import gee
            with st.spinner(t("checking")):
                try:
                    ee = gee.init()
                    for rid in monitor.MONITORED:
                        monitor.check_region(rid, ee=ee)
                    flash(t("check_done"))
                except BaseException as exc:  # noqa: BLE001 - gee.init exits with a message when it cannot start
                    flash(t("check_failed", e=exc), "error")
            st.rerun()
    else:
        st.code('$env:EE_SERVICE_ACCOUNT_KEY="E:\\keys\\safewindow-ee.json"; $env:EE_PROJECT="safewindow-2026"\n'
                "python scripts/daily_check.py", language="powershell")


def tab_phones() -> None:
    d = db()
    subs = {s["uid"]: s for s in alerts.load_subscriptions(d)}
    ids = sorted(alerts.load_test_ids(d))
    st.dataframe(pd.DataFrame([{t("col_phone"): uid, t("col_alerts_for"): subs.get(uid, {}).get("village", t("not_on")),
                                t("col_lang"): subs.get(uid, {}).get("lang", "")} for uid in ids]), hide_index=True)
    new = st.text_input(t("new_phone"))
    if st.button(t("add")) and new.strip():
        d.collection("test_devices").document(new.strip()).set({"added": pd.Timestamp.utcnow().to_pydatetime()})
        flash(t("added"))
        st.rerun()
    if ids:
        gone = st.selectbox(t("remove"), ids)
        if st.button(t("remove")):
            d.collection("test_devices").document(gone).delete()
            flash(t("removed"), "info")
            st.rerun()


def main() -> None:
    icon = Path(__file__).resolve().parent.parent / "pwa" / "public" / "icons" / "favicon-64.png"
    st.set_page_config(page_title="SafeWindow Admin", page_icon=str(icon) if icon.exists() else "🛡️", layout="wide")
    guard()
    st.sidebar.radio(text("bn", "language"), list(LANGS), format_func=LANGS.get, horizontal=True, key="admin_lang")
    st.title("🛡️ SafeWindow Admin")
    st.caption(t("subtitle") + ("" if alerts.live_allowed() else t("live_off")))
    admin = st.sidebar.text_input(t("your_name"), key="admin_name")
    if not admin.strip():
        st.info(t("name_needed"))
        st.stop()
    show_flash()
    try:
        all_alerts = alerts.load_alerts(db())
    except Exception as exc:  # noqa: BLE001 - say what is wrong instead of a stack trace
        st.error(t("firebase_failed", e=exc))
        st.stop()
    waiting = sum(r["status"] == "pending" for r in all_alerts)
    tabs = st.tabs([t("tab_new"), t("tab_approve", n=waiting), t("tab_log"), t("tab_monitor"), t("tab_forecast"),
                    t("tab_watch"), t("tab_demo"), t("tab_phones")])
    with tabs[0]:
        tab_new(admin)
    with tabs[1]:
        tab_approve(admin, all_alerts)
    with tabs[2]:
        tab_log(admin, all_alerts)
    with tabs[3]:
        tab_monitor()
    with tabs[4]:
        tab_forecast(admin, all_alerts)
    with tabs[5]:
        tab_watch(admin, all_alerts)
    with tabs[6]:
        tab_demo(admin)
    with tabs[7]:
        tab_phones()


if __name__ == "__main__":
    main()
