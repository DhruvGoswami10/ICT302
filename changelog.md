# Changelog

All notable changes to the Smart LMS Dashboard project.

## [1.1.0] — 2026-07-26

Model accuracy overhaul — honest out-of-fold evaluation, calibrated risk
bands, and a pruned feature set found by cross-validated search.

### Machine-learning engine
- **Accuracy 64.9% → 70.0%, ROC-AUC 0.699 → 0.761, at-risk recall 65% → 81%**
  (all out-of-fold, repeated stratified 5-fold CV over 5 shuffles).
- Pruned the 18-feature set to 10 via cross-validated search (greedy
  elimination + combination search, confirmed on fresh seeds and nested CV);
  added `feedback_viewed` and `late_events` features, dropped collinear
  volume counts that were adding noise at n=168.
- Count features now enter the model log-compressed (log1p) + robust-scaled.
- Sigmoid-calibrated probabilities: risk bands now read as real failure odds
  (out-of-fold, 87% of High-band students actually failed).
- `scored_students.json` now holds **out-of-fold** probabilities, so the
  dashboard's historical evidence shows generalisation, not training fit.
- Fixed the engagement component weights, which never matched the Excel
  export's component names (`Assignment`, `File`, …) — both naming schemes
  (export + live DB) are now covered.
- Week-cutoff models (wk 2–12) ship in the model bundle; the live scorer picks
  the one matching the cohort's elapsed weeks, and neutralises features the
  course structurally lacks (zero across the whole cohort) to the training
  median — live demo cohort no longer over-flagged as ~all High.
- Fixed the live scorer reading Unix timestamps as UTC: night/weekend
  features now use local (server) time, matching training.
- Early-warning and the historical replay now use the same repeated
  out-of-fold protocol (replay previously scored students the model was
  trained on and flagged nearly the whole cohort every week; it now flags
  ~2/3 with precision rising 0.59 → 0.72 across the term).
- Risk-band cutoffs are now derived from data at each retrain instead of the
  fixed 0.33/0.66 scale split: the High alert line is the highest threshold
  still catching ≥ 80% of actual failures out-of-fold (UC requirement —
  prefer false positives over missed students; it caught only 47% before,
  81% now), and the Low line requires a historical failure rate of at most
  half the cohort's base rate.
- Early-warning models now use the continuous-assessment columns of the
  results export that were previously ignored (10 weekly Assessed Exercise
  marks, Assignment 1 mark), restricted to what is known by each cutoff
  week; mid-term AUC rises to 0.79 by week 4 and 0.82 by week 8 (logs-only:
  0.67/0.71), and week-6 replay precision improves 0.66 → 0.80. The
  end-of-term model stays engagement-only since final marks derive from
  these assessments.

### Dashboard
- Engagement-vs-mark scatter: legend for the risk colours, dashed pass-mark
  line at 50, and a caption stating dots are out-of-sample predictions.
- Model page: accuracy, at-risk recall and High-band reliability KPIs plus
  the evaluation protocol note.

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
