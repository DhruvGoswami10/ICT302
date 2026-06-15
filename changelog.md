# Changelog

All notable changes to the Smart LMS Dashboard project.

## [1.0.0] — 2026-06-16

Initial working prototype — full pipeline from Moodle activity to live AI risk
flags on a shareable dashboard.

### Environment
- Provisioned the VM: Apache, MySQL 8.0, PHP 7.4, nginx, Python venv.
- Installed and configured **Moodle 4.1 LTS** (Apache on :8081, MySQL backend,
  cron enabled).

### Moodle content
- Created course **ICT001 Theory of Programming (S1, 2025)**.
- Added the Unit Coordinator account (`pcole`) and 20 student accounts
  (gender encoded by first name: John = male, Joy = female).
- Built 6 weekly sections with pages, URLs, forums, and 2 assignments.

### Machine-learning engine
- Feature engineering from 54k historical log rows joined to final results
  (`ml/lms_features.py`).
- Training pipeline comparing Logistic Regression / Random Forest / Gradient
  Boosting with 5-fold CV; logistic regression selected (ROC-AUC ≈ 0.70).
- Early-warning evaluation (weeks 2/4/6/8); AUC ≈ 0.77 by week 6.
- Engagement index (0–100) and explainable feature coefficients.
- Live scorer that reads the Moodle DB and writes `live_risk.json`
  (`ml/score_moodle.py`).

### Dashboard
- Flask JSON API exposing live cohort, activity timeline, recent feed, model
  metrics, early-warning curve and historical engagement-vs-outcome evidence.
- Auto-refreshing Chart.js front-end (KPIs, risk doughnut, timeline, scatter,
  early-warning bars, feature drivers, live student table + activity feed).
- Served by nginx; API run under gunicorn via systemd.
- Public sharing via a Cloudflare quick tunnel (systemd service).

### Moodle plugin
- `report_smartdashboard`: in-LMS report for the UC (engagement bars + AI risk
  bands per student), embedded live dashboard, on-demand scan button, and a
  **weekly scheduled risk-scan task**.

### Simulation
- `simulate_activity.py`: generates a re-runnable teaching period of demo
  activity across high/medium/low engagement profiles.
- `replay_historical.py`: week-by-week early-warning replay on the real cohort
  (≈88% of eventual failures flagged by week 2).

### Automation
- Cron: live rescore every minute; full retrain weekly (Sun 02:00).
- Moodle scheduled task: weekly risk scan (Sun 03:00).
