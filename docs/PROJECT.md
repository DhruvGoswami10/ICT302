# ICT302 — Smart LMS Dashboard

A Moodle-integrated analytics platform that lets a Unit Coordinator (UC) see
student engagement at a glance and uses a machine-learning model to flag
students at risk of failing **while the teaching period is still underway**.

Built for the ICT302 capstone. Client: Peter Cole, Murdoch University.

---

## 1. What it does

1. **Tracks engagement** for every enrolled student from Moodle's activity logs
   (views, submissions, forum activity, grade checks) — including students who
   are *not* engaging, which is the hardest group to see in stock Moodle.
2. **Scores at-risk students** with a scikit-learn model trained on a real
   historical cohort. This is an *algorithm-based* model, not an external AI API.
3. **Visualises everything** on a live, auto-refreshing web dashboard
   (PowerBI-style) and inside Moodle itself via a custom report plugin.
4. **Re-scores in real time** (every minute) and runs a full **weekly scan**.
5. **Simulates** a whole teaching period so the system can be demonstrated and
   validated end-to-end.

---

## 2. Architecture

```
            Students / UC (browser)
                     │
     ┌───────────────┴───────────────┐
     │                               │
 Moodle 4.1 LMS                 Smart LMS Dashboard
 (Apache, :8081)                (nginx :80  ──►  Flask/gunicorn :5000)
     │  mdl_logstore_standard_log          ▲
     │  (real activity events)             │ reads
     └──────────────┬─────────────────────┘
                    │
            scikit-learn engine (Python venv)
            ├─ train_model.py   (historical training → model + metrics)
            ├─ score_moodle.py  (live scoring → live_risk.json)   ← cron, every minute
            └─ simulate / replay (teaching-period simulation)

 Public access: Cloudflare quick tunnel  ──►  nginx :80
```

### Components

| Path | What it is |
|------|------------|
| `ml/lms_features.py` | Data loading + engagement feature engineering |
| `ml/train_model.py` | Trains/compares models, writes artifacts to `ml/models/` |
| `ml/score_moodle.py` | Scores the live Moodle cohort → `ml/models/live_risk.json` |
| `dashboard/api.py` | Flask JSON API (live + historical + model metrics) |
| `dashboard/index.html`, `app.js` | Auto-refreshing Chart.js dashboard |
| `moodle-plugin/report/smartdashboard/` | Moodle report plugin (in-LMS view + weekly task) |
| `simulation/simulate_activity.py` | Generates a teaching period of demo activity |
| `simulation/replay_historical.py` | Week-by-week early-warning replay on real data |
| `setup/` | Install + bootstrap scripts |

---

## 3. The data

Two anonymised, released exports from ICT001 *Theory of Programming* (S1 2025):

- `data/logs.xlsx` — 54,812 Moodle event-log rows (168 students).
- `data/results.xlsx` — final marks / grades.

**Join key:** the number in `SurnameNNN`, present in both files.
**Gender** is encoded by the anonymised first name: **John = male, Joy = female**
(139 male / 29 female). Gender is used as a model feature and for a fairness lens.

Label: a student is **at risk** if final grade is `N` (fail) or final mark < 50.
Cohort at-risk rate: **58%** (a genuinely high-failure unit).

---

## 4. The model

- Compares Logistic Regression, Random Forest, Gradient Boosting with 5-fold
  stratified CV; **logistic regression wins (ROC-AUC ≈ 0.70)** and generalises
  best on this small cohort.
- **Engagement features:** total & component-weighted events, active days/weeks,
  events per active day, night/weekend activity, assignment/quiz/forum/resource
  events, grade checks, submissions, breadth of activity, early-weeks activity,
  last active week, gender.
- **Engagement index (0–100):** weighted activity + consistency + breadth.
- **Early warning:** trained on cumulative data up to weeks 2/4/6/8 — AUC rises
  to **0.77 by week 6**, i.e. it gets reliable early in the term.
- **Explainability:** coefficients exported to `ml/models/feature_importances.json`
  (low active-weeks / few submissions / few assignment events → higher risk).
- Risk bands: High ≥ 0.66, Medium 0.33–0.66, Low < 0.33.

Artifacts (in `ml/models/`): `risk_model.joblib`, `metrics.json`,
`feature_importances.json`, `early_warning.json`, `scored_students.json`.

---

## 5. Running it

### Live URLs (this VM)
- **Dashboard (local):** http://10.51.33.70/
- **Dashboard (public):** Cloudflare quick tunnel — see `setup/` notes; the
  URL changes when the tunnel service restarts. Retrieve the current one with:
  `sudo grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /var/log/smartlms-tunnel.log | tail -1`
- **Moodle LMS:** http://10.51.33.70:8081/

### Accounts
| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `Admin#2026pw` |
| Unit Coordinator (teacher) | `pcole` | `Teach#2026pw` |
| Students | `student001` … `student020` | `Stud#2026pw` |

(Credentials are for the local demo VM only.)

### Services (systemd)
- `smartlms-api` — gunicorn API on 127.0.0.1:5000
- `nginx` — serves the dashboard + proxies `/api`
- `smartlms-tunnel` — Cloudflare public tunnel
- `apache2` — Moodle (:8081), `mysql` — database

### Scheduled jobs
- **Every minute** (cron): `score_moodle.py` → refreshes live risk.
- **Weekly Sun 02:00** (cron): `train_model.py` → full retrain.
- **Weekly Sun 03:00** (Moodle scheduled task): `report_smartdashboard\task\risk_scan`.

### Common commands
```bash
# retrain on historical data
venv/bin/python ml/train_model.py
# rescore the live cohort now
venv/bin/python ml/score_moodle.py
# simulate a teaching period of activity (re-runnable)
venv/bin/python simulation/simulate_activity.py
# week-by-week early-warning replay on real data
venv/bin/python simulation/replay_historical.py
```

### Rebuild from scratch
See `setup/` — installs PHP/MySQL/Apache/nginx, Moodle 4.1, the Python venv,
the course + accounts, and deploys the plugin.

---

## 6. Stack

Ubuntu 20.04 · Moodle 4.1 LTS · PHP 7.4 · MySQL 8.0 · Apache + nginx ·
Python 3.8 (scikit-learn, pandas, Flask, gunicorn, pymysql) · Chart.js ·
Cloudflare Tunnel.

---

## 7. Roadmap / known limitations

- Live demo cohort is 20 accounts; the model is trained on the full 168-student
  historical cohort.
- Public tunnel URL is ephemeral (a named Cloudflare tunnel needs a domain).
- Model AUC (~0.70) reflects engagement-only signals on a high-failure unit;
  adding assessment-timeliness and engagement-trend features should improve it.
- DB credentials in source are for the local demo only and should be moved to
  environment variables for any real deployment.
