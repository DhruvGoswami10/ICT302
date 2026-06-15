"""
Data loading + feature engineering for the Smart LMS at-risk model.

Two historical sources (anonymised real Moodle export for ICT001 S1 2025):
  - data/logs.xlsx     : 54k Moodle event-log rows
  - data/results.xlsx  : final marks / grades per student

Join key: the number in "SurnameNNN" (present in both files).
Gender is encoded by the anonymised first name: John = male, Joy = female.
"""
import re
import numpy as np
import pandas as pd

DATA_DIR = "/home/td05/ict302/data"

# --- engagement weighting per Moodle component (how much an event "counts") ---
COMPONENT_WEIGHT = {
    "mod_assign": 3.0, "assign": 3.0,
    "mod_quiz": 3.0, "quiz": 3.0,
    "mod_forum": 2.0, "forum": 2.0,
    "mod_resource": 1.5, "resource": 1.5, "File": 1.5, "mod_url": 1.2, "url": 1.2,
    "mod_page": 1.2, "page": 1.2,
}


def _sid_from_name(name):
    """Extract the student number from 'John Surname046' -> 46."""
    if not isinstance(name, str):
        return None
    m = re.search(r"Surname0*(\d+)", name)
    return int(m.group(1)) if m else None


def _gender_from_name(name):
    if isinstance(name, str):
        t = name.strip().split(" ")[0].lower()
        if t == "john":
            return "M"
        if t == "joy":
            return "F"
    return "U"


def load_logs():
    df = pd.read_excel(f"{DATA_DIR}/logs.xlsx", engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    df["sid"] = df["User full name"].apply(_sid_from_name)
    df["gender"] = df["User full name"].apply(_gender_from_name)
    df = df[df["sid"].notna()].copy()
    df["sid"] = df["sid"].astype(int)
    # Moodle export time format: DD/MM/YY, HH:MM:SS
    df["ts"] = pd.to_datetime(df["Time"], format="%d/%m/%y, %H:%M:%S", errors="coerce")
    df = df[df["ts"].notna()].copy()
    return df


def load_results():
    # header is on the 3rd row (two metadata rows above it)
    df = pd.read_excel(f"{DATA_DIR}/results.xlsx", engine="openpyxl", header=2)
    df.columns = [str(c).strip() for c in df.columns]
    df = df[df["Surname"].astype(str).str.contains("Surname", na=False)].copy()
    df["sid"] = df["Surname"].apply(lambda s: int(re.search(r"0*(\d+)", str(s)).group(1)))
    df["mark"] = pd.to_numeric(df["Mark"], errors="coerce")
    df["grade"] = df["Grade"].astype(str).str.strip()
    # at-risk / fail label: grade N (fail) or final mark < 50
    df["at_risk"] = (((df["grade"] == "N") | (df["mark"] < 50))).astype(int)
    return df[["sid", "mark", "grade", "at_risk"]]


def teaching_window(logs):
    """Return (start, end) of the teaching period (robust to outlier dates)."""
    q_lo = logs["ts"].quantile(0.01)
    q_hi = logs["ts"].quantile(0.99)
    return q_lo.normalize(), q_hi.normalize()


def build_features(logs, cutoff=None, start=None):
    """
    Build per-student engagement features from the log rows.
    If `cutoff` is given, only events up to that timestamp are used
    (this is what powers early-warning + the week-by-week simulation).
    """
    if start is None:
        start, _ = teaching_window(logs)
    d = logs if cutoff is None else logs[logs["ts"] <= cutoff]
    d = d[d["ts"] >= start]

    rows = []
    comp = d["Component"].astype(str)
    ename = d["Event name"].astype(str)
    for sid, g in d.groupby("sid"):
        gc = g["Component"].astype(str)
        ge = g["Event name"].astype(str)
        days = g["ts"].dt.normalize()
        hours = g["ts"].dt.hour
        weeks = ((g["ts"] - start).dt.days // 7)
        span = (g["ts"].max() - g["ts"].min()).total_seconds() / 86400.0
        n = len(g)
        weighted = sum(COMPONENT_WEIGHT.get(c, 1.0) for c in gc)
        rows.append({
            "sid": sid,
            "gender": g["gender"].mode().iat[0] if len(g["gender"].mode()) else "U",
            "total_events": n,
            "weighted_events": weighted,
            "active_days": days.nunique(),
            "active_weeks": weeks.nunique(),
            "span_days": span,
            "events_per_active_day": n / max(1, days.nunique()),
            "night_events": int((hours < 6).sum()),
            "weekend_events": int((g["ts"].dt.dayofweek >= 5).sum()),
            "assign_events": int(gc.str.contains("assign", case=False).sum()),
            "quiz_events": int(gc.str.contains("quiz", case=False).sum()),
            "forum_events": int(gc.str.contains("forum", case=False).sum()),
            "resource_events": int(gc.str.contains("resource|file|url|page", case=False).sum()),
            "grade_checks": int(ge.str.contains("grade", case=False).sum()),
            "submissions": int(ge.str.contains("submitted", case=False).sum()),
            "distinct_event_types": ge.nunique(),
            "early_events": int((weeks <= 1).sum()),         # first 2 weeks
            "last_week_active": int(weeks.max()) if n else 0,
        })
    feat = pd.DataFrame(rows)
    return feat


def engagement_score(feat):
    """0-100 engagement index from weighted activity, breadth and consistency."""
    f = feat.copy()
    def norm(col):
        v = f[col].astype(float)
        return (v - v.min()) / (v.max() - v.min() + 1e-9)
    score = (0.45 * norm("weighted_events")
             + 0.30 * norm("active_weeks")
             + 0.15 * norm("distinct_event_types")
             + 0.10 * norm("events_per_active_day"))
    return (100 * score).round(1)


FEATURE_COLS = [
    "total_events", "weighted_events", "active_days", "active_weeks", "span_days",
    "events_per_active_day", "night_events", "weekend_events", "assign_events",
    "quiz_events", "forum_events", "resource_events", "grade_checks", "submissions",
    "distinct_event_types", "early_events", "last_week_active", "gender_M",
]


def to_matrix(feat):
    f = feat.copy()
    f["gender_M"] = (f["gender"] == "M").astype(int)
    for c in FEATURE_COLS:
        if c not in f.columns:
            f[c] = 0
    return f[FEATURE_COLS].fillna(0.0)
