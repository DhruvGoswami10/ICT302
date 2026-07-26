"""
Score the LIVE Moodle cohort with the trained at-risk model.

Reads enrolled students + their real events from the Moodle database
(mdl_logstore_standard_log), builds the same feature schema used in training,
and writes models/live_risk.json for the dashboard.

This is what makes the dashboard "live": run it on a schedule (cron / Moodle
scheduled task) or on demand and the dashboard reflects current engagement.
"""
import json
import re
from datetime import datetime

import pandas as pd
import pymysql
import joblib

import lms_features as L

DB = dict(host="127.0.0.1", user="moodleuser", password="Moodle#2026db",
          database="moodle", charset="utf8mb4")
COURSE_SHORT = "ICT001"
OUT = "/home/td05/ict302/ml/models"


def fetch():
    conn = pymysql.connect(**DB)
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id FROM mdl_course WHERE shortname=%s", (COURSE_SHORT,))
    course = cur.fetchone()
    courseid = course["id"]

    # enrolled students (role student = 5)
    cur.execute("""
        SELECT u.id, u.username, u.firstname, u.lastname
        FROM mdl_user u
        JOIN mdl_user_enrolments ue ON ue.userid=u.id
        JOIN mdl_enrol e ON e.id=ue.enrolid AND e.courseid=%s
        JOIN mdl_context ctx ON ctx.instanceid=%s AND ctx.contextlevel=50
        JOIN mdl_role_assignments ra ON ra.userid=u.id AND ra.contextid=ctx.id AND ra.roleid=5
        GROUP BY u.id
    """, (courseid, courseid))
    students = cur.fetchall()

    # all events in this course for those users
    cur.execute("""
        SELECT l.userid, l.component, l.eventname, l.timecreated
        FROM mdl_logstore_standard_log l
        WHERE l.courseid=%s
    """, (courseid,))
    events = cur.fetchall()
    conn.close()
    return courseid, students, events


def sid_of(username):
    m = re.search(r"(\d+)", username or "")
    return int(m.group(1)) if m else None


def main():
    courseid, students, events = fetch()
    umap = {s["id"]: s for s in students}

    # timecreated is a unix timestamp (UTC); convert to server-local time so
    # night/weekend features mean local nights and weekends, matching training
    local_tz = datetime.now().astimezone().tzinfo
    rows = []
    for e in events:
        s = umap.get(e["userid"])
        if not s:
            continue
        rows.append({
            "User full name": f"{s['firstname']} {s['lastname']}",
            "Component": e["component"] or "",
            "Event name": e["eventname"] or "",
            "ts": pd.to_datetime(e["timecreated"], unit="s", utc=True)
                    .tz_convert(local_tz).tz_localize(None),
            "sid": sid_of(s["username"]),
            "gender": "M" if s["firstname"].strip().lower() == "john" else
                      ("F" if s["firstname"].strip().lower() == "joy" else "U"),
        })
    logs = pd.DataFrame(rows)

    bundle = joblib.load(f"{OUT}/risk_model.joblib")
    model = bundle["model"]
    week_models = bundle.get("week_models", {})

    # ensure every enrolled student appears even with zero activity
    all_sids = {sid_of(s["username"]): s for s in students}
    if len(logs):
        start = logs["ts"].min().normalize()
        feat = L.build_features(logs, start=start)
        # mid-term cohort: score with the historical model trained on a data
        # window of matching length, so feature scales line up (see train_model)
        elapsed = (logs["ts"].max() - start).days / 7.0
        term_weeks = (pd.to_datetime(bundle["end"]) - pd.to_datetime(bundle["start"])).days / 7.0
        if week_models and elapsed < term_weeks - 1:
            fits = [w for w in sorted(week_models) if w <= elapsed]
            wk = fits[-1] if fits else min(week_models)
            model = week_models[wk]
            print(f"cohort at week {elapsed:.1f} of ~{term_weeks:.0f} -> using week-{wk} model")
    else:
        feat = pd.DataFrame()

    present = set(feat["sid"]) if len(feat) else set()
    blanks = []
    for sid, s in all_sids.items():
        if sid not in present:
            blanks.append({"sid": sid, "gender": "M" if s["firstname"].lower() == "john" else "F",
                           "total_events": 0, "weighted_events": 0, "active_days": 0,
                           "active_weeks": 0, "span_days": 0, "events_per_active_day": 0,
                           "night_events": 0, "weekend_events": 0, "assign_events": 0,
                           "quiz_events": 0, "forum_events": 0, "resource_events": 0,
                           "grade_checks": 0, "submissions": 0, "feedback_viewed": 0,
                           "distinct_event_types": 0, "early_events": 0, "late_events": 0,
                           "last_week_active": 0})
    if blanks:
        feat = pd.concat([feat, pd.DataFrame(blanks)], ignore_index=True)

    feat["engagement"] = L.engagement_score(feat) if len(feat) > 1 else 0.0
    X = L.to_matrix(feat)
    # a feature that is zero for the ENTIRE cohort means the course doesn't
    # offer that signal (e.g. no feedback released yet) — neutralise it to the
    # training median rather than reading it as every student disengaging
    for c, m in bundle.get("feature_medians", {}).items():
        if c in X.columns and len(X) and X[c].max() == 0:
            X[c] = m
    proba = model.predict_proba(X)[:, 1]
    feat["risk_prob"] = proba.round(4)
    # band cutoffs are derived from data at train time (see train_model.py)
    bands = bundle.get("bands", {"low": 0.33, "high": 0.66})
    feat["risk_band"] = pd.cut(feat["risk_prob"], [-0.01, bands["low"], bands["high"], 1.01],
                               labels=["Low", "Medium", "High"]).astype(str)
    # attach display names
    name_by_sid = {sid_of(s["username"]): f"{s['firstname']} {s['lastname']}" for s in students}
    feat["name"] = feat["sid"].map(name_by_sid)

    out = feat.sort_values("risk_prob", ascending=False)[
        ["sid", "name", "gender", "engagement", "total_events", "active_weeks",
         "assign_events", "forum_events", "grade_checks", "risk_prob", "risk_band"]]
    # atomic write (+world rw) so both the cron user and Moodle's www-data can refresh it
    import os
    tmp = f"{OUT}/.live_risk.{os.getpid()}.json"
    out.to_json(tmp, orient="records")
    os.chmod(tmp, 0o666)
    os.replace(tmp, f"{OUT}/live_risk.json")
    print(f"Scored {len(out)} live students; {(out.risk_band=='High').sum()} High-risk. -> {OUT}/live_risk.json")


if __name__ == "__main__":
    main()
