"""
Smart LMS Dashboard API (Flask).

Serves live + historical analytics as JSON:
  - live risk/engagement of the Moodle cohort (from models/live_risk.json)
  - real-time activity feed + timeline straight from the Moodle DB
  - the trained model's metrics, drivers and early-warning curve
  - historical engagement-vs-outcome evidence

Runs behind nginx (which serves the static dashboard and proxies /api/*).
"""
import json
import os
import pymysql
from flask import Flask, jsonify

MODELS = "/home/td05/ict302/ml/models"
DB = dict(host="127.0.0.1", user="moodleuser", password="Moodle#2026db",
          database="moodle", charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
COURSE_SHORT = "ICT001"

app = Flask(__name__)


def load(name, default):
    p = os.path.join(MODELS, name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return default


def db():
    return pymysql.connect(**DB)


def course_id(cur):
    cur.execute("SELECT id FROM mdl_course WHERE shortname=%s", (COURSE_SHORT,))
    r = cur.fetchone()
    return r["id"] if r else None


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/api/health")
def health():
    return jsonify(status="ok")


@app.route("/api/overview")
def overview():
    live = load("live_risk.json", [])
    metrics = load("metrics.json", {})
    bands = {"High": 0, "Medium": 0, "Low": 0}
    eng_sum, gender = 0.0, {"M": 0, "F": 0, "U": 0}
    for s in live:
        bands[s.get("risk_band", "Low")] = bands.get(s.get("risk_band", "Low"), 0) + 1
        eng_sum += s.get("engagement", 0) or 0
        gender[s.get("gender", "U")] = gender.get(s.get("gender", "U"), 0) + 1
    n = max(1, len(live))
    last_updated = None
    p = os.path.join(MODELS, "live_risk.json")
    if os.path.exists(p):
        last_updated = int(os.path.getmtime(p))
    return jsonify(
        total_students=len(live),
        risk_bands=bands,
        avg_engagement=round(eng_sum / n, 1),
        gender=gender,
        model={"chosen": metrics.get("chosen"),
               "auc": (metrics.get("models", {}).get(metrics.get("chosen", ""), {}) or {}).get("roc_auc"),
               "historical_at_risk_rate": metrics.get("at_risk_rate"),
               "n_train": metrics.get("n_students")},
        last_updated=last_updated,
    )


@app.route("/api/students")
def students():
    return jsonify(load("live_risk.json", []))


@app.route("/api/historical")
def historical():
    return jsonify(load("scored_students.json", []))


@app.route("/api/feature_importances")
def importances():
    return jsonify(load("feature_importances.json", {}))


@app.route("/api/early_warning")
def early_warning():
    return jsonify(load("early_warning.json", {}))


@app.route("/api/metrics")
def metrics():
    return jsonify(load("metrics.json", {}))


@app.route("/api/timeline")
def timeline():
    """Events per day in the course (live, last 30 active days)."""
    conn = db()
    try:
        cur = conn.cursor()
        cid = course_id(cur)
        if not cid:
            return jsonify([])
        cur.execute("""
            SELECT FROM_UNIXTIME(timecreated,'%%Y-%%m-%%d') AS day, COUNT(*) AS events
            FROM mdl_logstore_standard_log WHERE courseid=%s
            GROUP BY day ORDER BY day DESC LIMIT 30
        """, (cid,))
        rows = list(reversed(cur.fetchall()))
        return jsonify(rows)
    finally:
        conn.close()


@app.route("/api/recent")
def recent():
    """Live activity feed: latest events with student + action."""
    conn = db()
    try:
        cur = conn.cursor()
        cid = course_id(cur)
        if not cid:
            return jsonify([])
        cur.execute("""
            SELECT FROM_UNIXTIME(l.timecreated,'%%Y-%%m-%%d %%H:%%i:%%s') AS time,
                   CONCAT(u.firstname,' ',u.lastname) AS student,
                   l.action, l.target, l.component
            FROM mdl_logstore_standard_log l
            JOIN mdl_user u ON u.id=l.userid
            WHERE l.courseid=%s AND l.userid>2
            ORDER BY l.timecreated DESC LIMIT 25
        """, (cid,))
        return jsonify(cur.fetchall())
    finally:
        conn.close()


@app.route("/api/engagement_outcome")
def engagement_outcome():
    """Historical proof: engagement index vs final mark (+ risk band)."""
    hist = load("scored_students.json", [])
    pts = [{"engagement": h.get("engagement"), "mark": h.get("mark"),
            "risk_band": h.get("risk_band"), "grade": h.get("grade")}
           for h in hist if h.get("mark") is not None]
    return jsonify(pts)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
