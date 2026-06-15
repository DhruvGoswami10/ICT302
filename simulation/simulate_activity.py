"""
Simulate a teaching period of Moodle activity for the demo cohort.

Generates realistic events (course views, module views, submissions, grade
checks) for each enrolled student according to an engagement profile, spread
across the teaching weeks. Events are written into mdl_logstore_standard_log
exactly like real Moodle activity, so the live scorer + dashboard react to them.

Profiles:
  high   -> engaged all term            -> Low risk
  medium -> moderate, some weeks missed -> Medium risk
  low    -> active early then drops off  -> High risk (early-warning signal)

Re-runnable: previously simulated rows (tagged in `other`) are cleared first.
Pure simulation — no real student data is used here.
"""
import json
import random
from datetime import datetime, timedelta
import pymysql

DB = dict(host="127.0.0.1", user="moodleuser", password="Moodle#2026db",
          database="moodle", charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
COURSE_SHORT = "ICT001"
SIM_TAG = '{"sim":true}'
TERM_START = datetime(2025, 3, 21)
WEEKS = 12
random.seed(42)

PROFILES = {
    "high":   dict(weeks=range(0, WEEKS),   per_week=(12, 20), submit=0.7, gradecheck=0.5),
    "medium": dict(weeks=range(0, WEEKS, 1), per_week=(4, 9),  submit=0.4, gradecheck=0.3),
    "low":    dict(weeks=range(0, 4),       per_week=(0, 3),   submit=0.05, gradecheck=0.1),
}


def assign_profile(i):
    return ["high", "medium", "low", "medium", "high", "low",
            "medium", "high", "low", "medium"][i % 10]


def main():
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT id FROM mdl_course WHERE shortname=%s", (COURSE_SHORT,))
    courseid = cur.fetchone()["id"]
    cur.execute("SELECT id FROM mdl_context WHERE contextlevel=50 AND instanceid=%s", (courseid,))
    coursectx = cur.fetchone()["id"]

    cur.execute("""
        SELECT cm.id cmid, m.name modname, cm.instance,
               ctx.id contextid
        FROM mdl_course_modules cm
        JOIN mdl_modules m ON m.id=cm.module
        JOIN mdl_context ctx ON ctx.contextlevel=70 AND ctx.instanceid=cm.id
        WHERE cm.course=%s
    """, (courseid,))
    mods = cur.fetchall()
    assigns = [m for m in mods if m["modname"] == "assign"]
    viewables = [m for m in mods if m["modname"] in ("page", "url", "forum")]

    cur.execute("""
        SELECT u.id, u.username, u.firstname
        FROM mdl_user u
        JOIN mdl_user_enrolments ue ON ue.userid=u.id
        JOIN mdl_enrol e ON e.id=ue.enrolid AND e.courseid=%s
        JOIN mdl_role_assignments ra ON ra.userid=u.id
        JOIN mdl_context ctx ON ctx.id=ra.contextid AND ctx.contextlevel=50 AND ctx.instanceid=%s
        WHERE ra.roleid=5 GROUP BY u.id ORDER BY u.username
    """, (courseid, courseid))
    students = cur.fetchall()

    # wipe previous simulation
    cur.execute("DELETE FROM mdl_logstore_standard_log WHERE courseid=%s AND other=%s",
                (courseid, SIM_TAG))
    conn.commit()

    rows = []

    def ev(userid, ts, eventname, component, action, target, ctxid, ctxlevel, ctxinst,
           objecttable=None, objectid=None, crud="r", edulevel=2):
        rows.append((eventname, component, action, target, objecttable, objectid, crud,
                     edulevel, ctxid, ctxlevel, ctxinst, userid, courseid, None, 0,
                     SIM_TAG, int(ts.timestamp()), "web",
                     "10.0.%d.%d" % (random.randint(1, 254), random.randint(1, 254)), None))

    for i, s in enumerate(students):
        prof = PROFILES[assign_profile(i)]
        uid = s["id"]
        for w in prof["weeks"]:
            n = random.randint(*prof["per_week"])
            for _ in range(n):
                day = TERM_START + timedelta(weeks=w, days=random.randint(0, 6),
                                             hours=random.randint(7, 23),
                                             minutes=random.randint(0, 59))
                roll = random.random()
                if roll < 0.25:
                    ev(uid, day, r"\core\event\course_viewed", "core", "viewed", "course",
                       coursectx, 50, courseid)
                elif roll < 0.9 and viewables:
                    m = random.choice(viewables)
                    ev(uid, day, r"\mod_%s\event\course_module_viewed" % m["modname"],
                       "mod_%s" % m["modname"], "viewed", "course_module",
                       m["contextid"], 70, m["cmid"], m["modname"], m["instance"])
                else:
                    ev(uid, day, r"\gradereport_user\event\grade_report_viewed",
                       "gradereport_user", "viewed", "grade_report", coursectx, 50, courseid)
            if random.random() < prof["gradecheck"]:
                day = TERM_START + timedelta(weeks=w, days=random.randint(0, 6), hours=20)
                ev(uid, day, r"\gradereport_user\event\grade_report_viewed",
                   "gradereport_user", "viewed", "grade_report", coursectx, 50, courseid)
        # assignment submissions for engaged students
        if assigns and random.random() < prof["submit"]:
            for a in assigns:
                day = TERM_START + timedelta(weeks=random.randint(4, 9), days=random.randint(0, 6), hours=22)
                ev(uid, day, r"\mod_assign\event\assessable_submitted", "mod_assign",
                   "submitted", "assessable", a["contextid"], 70, a["cmid"],
                   "assign_submission", a["instance"], crud="u")

    sql = """INSERT INTO mdl_logstore_standard_log
        (eventname,component,action,target,objecttable,objectid,crud,edulevel,
         contextid,contextlevel,contextinstanceid,userid,courseid,relateduserid,
         anonymous,other,timecreated,origin,ip,realuserid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    cur.executemany(sql, rows)
    conn.commit()
    print(f"Inserted {len(rows)} simulated events for {len(students)} students "
          f"across {WEEKS} weeks.")
    # profile summary
    summary = {}
    for i, s in enumerate(students):
        summary.setdefault(assign_profile(i), []).append(s["username"])
    for k, v in summary.items():
        print(f"  {k:6s}: {len(v)} students")
    conn.close()


if __name__ == "__main__":
    main()
