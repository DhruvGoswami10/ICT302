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
(139 male / 29 female). Gender is a reporting/fairness lens only — it was
removed as a model feature after an ablation showed it added no out-of-fold
AUC and is uncorrelated with every other feature.

Label: a student is **at risk** if final grade is `N` (fail) or final mark < 50.
Cohort at-risk rate: **58%** (a genuinely high-failure unit).

---

## 4. The model

- Compares Logistic Regression, Random Forest, Gradient Boosting (each
  sigmoid-calibrated) with repeated stratified 5-fold CV — 5 shuffles, every
  reported number out-of-fold; **logistic regression wins (ROC-AUC ≈ 0.76,
  accuracy ≈ 0.70, at-risk recall ≈ 0.78)**.
- **Model features (9):** active days, night & weekend events, submissions,
  breadth of event types, last active week, feedback views, final-4-weeks
  activity, resource events. Chosen by cross-validated search (greedy
  elimination + cross-family combining, confirmed on fresh seeds and nested
  CV); the dropped volume counts were collinear noise at n=168, and gender
  was removed after ablation (no AUC contribution — see §3). Counts enter
  the model log-compressed (log1p) then robust-scaled.
- **Calibrated probabilities:** sigmoid calibration, so predicted
  probabilities read as real failure odds. The Low band is *absence of
  alarm*, not a pass guarantee.
- **Honest scoring:** `scored_students.json` holds out-of-fold probabilities
  (the model never saw the student it scores), so the dashboard's historical
  evidence shows genuine generalisation, not training-set fit.
- **Engagement index (0–100):** weighted activity + consistency + breadth
  (component weights cover both the Excel export's and the live DB's naming).
- **Early warning:** cumulative data up to weeks 2/4/6/8/10/12, same OOF
  protocol, behavioral features only — assessment marks are never model
  inputs, in the week-cutoff models or anywhere else: a mark is a component
  of the final total that defines the at-risk label, so using it would leak
  the answer into the prediction. AUC rises **0.59 → 0.71 by week 8 → 0.76
  by week 10**. Week-cutoff models ship in the bundle: the live scorer picks
  the one matching the cohort's elapsed weeks, and neutralises features the
  course structurally lacks (zero across the whole cohort, e.g. no feedback
  released) to the training median.
- **Explainability:** coefficients exported to `ml/models/feature_importances.json`
  (few active days / no feedback views / little late-term activity → higher risk).
- **Risk-band cutoffs are derived from the data at every retrain**, not fixed
  splits of the scale: the High alert line is the highest threshold that still
  catches **≥ 60% of actual failures** out-of-fold — the operating point sits
  just before the precision cliff, balancing the prefer-false-positives
  requirement against alert quality (currently ≈ 0.60, catching 60% of
  failures at 84% precision); the Low line is the highest threshold whose band
  historically fails at no more than half the cohort's base rate (≈ 0.46).

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
- Model AUC (~0.76) reflects engagement-only signals on a high-failure unit;
  the model certifies *risk* well but cannot certify *safety* — a disengaged
  student who passes anyway is invisible to it, so the Low band means
  "historically fails at under half the cohort rate", not "will pass".
- DB credentials in source are for the local demo only and should be moved to
  environment variables for any real deployment.
