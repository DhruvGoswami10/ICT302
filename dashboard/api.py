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
    # serialize in week order: jsonify would sort keys alphabetically,
    # putting week_10 before week_2
    ew = load("early_warning.json", {})
    ordered = {k: ew[k] for k in sorted(ew, key=lambda k: int(k.rsplit("_", 1)[-1]))}
    return app.response_class(json.dumps(ordered), mimetype="application/json")


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


@app.route("/api/student/<int:sid>")
def student_detail(sid):
    """Full activity history for one student (sid = the number in studentNNN)."""
    conn = db()
    try:
        cur = conn.cursor()
        cid = course_id(cur)
        if not cid:
            return jsonify([])
        cur.execute("""
            SELECT FROM_UNIXTIME(l.timecreated,'%%Y-%%m-%%d %%H:%%i:%%s') AS time,
                   l.action, l.target, l.component
            FROM mdl_logstore_standard_log l
            JOIN mdl_user u ON u.id=l.userid
            WHERE l.courseid=%s
              AND CAST(REGEXP_REPLACE(u.username,'[^0-9]','') AS UNSIGNED)=%s
            ORDER BY l.timecreated DESC LIMIT 200
        """, (cid, sid))
        return jsonify(cur.fetchall())
    finally:
        conn.close()


@app.route("/api/assignments")
def assignments():
    """Per-assignment submission counts vs the enrolled student cohort."""
    conn = db()
    try:
        cur = conn.cursor()
        cid = course_id(cur)
        if not cid:
            return jsonify([])
        cur.execute("""
            SELECT a.id, a.name, a.duedate,
                   (SELECT COUNT(DISTINCT ra.userid) FROM mdl_role_assignments ra
                    JOIN mdl_context ctx ON ctx.id=ra.contextid
                         AND ctx.contextlevel=50 AND ctx.instanceid=%s
                    WHERE ra.roleid=5) as total
            FROM mdl_assign a
            WHERE a.course=%s
            ORDER BY a.duedate ASC
        """, (cid, cid))
        rows = cur.fetchall()
        # who submitted: the submission table is authoritative, but simulated
        # activity only exists in the event log — union both sources
        cur.execute("""
            SELECT s.assignment AS aid, s.userid FROM mdl_assign_submission s
            JOIN mdl_assign a ON a.id=s.assignment
            WHERE a.course=%s AND s.status='submitted' AND s.latest=1
        """, (cid,))
        submitted_by = {}
        for r in cur.fetchall():
            submitted_by.setdefault(r["aid"], set()).add(r["userid"])
        cur.execute("""
            SELECT cm.instance AS aid, l.userid
            FROM mdl_logstore_standard_log l
            JOIN mdl_course_modules cm ON cm.id=l.contextinstanceid AND l.contextlevel=70
            JOIN mdl_modules m ON m.id=cm.module AND m.name='assign'
            WHERE l.courseid=%s AND l.eventname LIKE '%%assessable_submitted%%'
        """, (cid,))
        for r in cur.fetchall():
            submitted_by.setdefault(r["aid"], set()).add(r["userid"])
        result = []
        for r in rows:
            total = r["total"] or 1
            submitted = len(submitted_by.get(r["id"], ()))
            result.append({
                "name": r["name"],
                "duedate": r["duedate"],
                "submitted": submitted,
                "total": total,
                "percentage": (submitted / total) * 100,
            })
        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/resources")
def resources():
    """Viewable course content (pages, urls, forums, files) — excludes assignments/quizzes."""
    conn = db()
    try:
        cur = conn.cursor()
        cid = course_id(cur)
        if not cid:
            return jsonify([])
        cur.execute("""
            SELECT cm.id, m.name as type,
                   COALESCE(r.name, u.name, p.name, f.name, cm.id) as name,
                   (SELECT COUNT(*) FROM mdl_logstore_standard_log l
                    WHERE l.contextinstanceid = cm.id AND l.contextlevel = 70
                      AND l.eventname LIKE '%%course_module_viewed%%'
                      AND l.userid > 2) as views
            FROM mdl_course_modules cm
            JOIN mdl_modules m ON m.id=cm.module
            LEFT JOIN mdl_resource r ON r.id=cm.instance AND m.name='resource'
            LEFT JOIN mdl_url u ON u.id=cm.instance AND m.name='url'
            LEFT JOIN mdl_page p ON p.id=cm.instance AND m.name='page'
            LEFT JOIN mdl_forum f ON f.id=cm.instance AND m.name='forum'
            WHERE cm.course=%s AND cm.visible=1
            AND m.name NOT IN ('assign','quiz','label')
            ORDER BY cm.section, cm.id
        """, (cid,))
        return jsonify(cur.fetchall())
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
