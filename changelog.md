# Changelog

All notable changes to the Smart LMS Dashboard project.

## [1.1.0] — 2026-07-26

Model accuracy overhaul — honest out-of-fold evaluation, calibrated risk
bands, and a pruned feature set found by cross-validated search.

### Machine-learning engine
- **Accuracy 64.9% → 70.5%, ROC-AUC 0.699 → 0.760, at-risk recall 65% → 78%**
  (all out-of-fold, repeated stratified 5-fold CV over 5 shuffles).
- Pruned the 18-feature set to 9 via cross-validated search (greedy
  elimination + combination search, confirmed on fresh seeds and nested CV);
  added `feedback_viewed` and `late_events` features, dropped collinear
  volume counts that were adding noise at n=168.
- Gender removed as a model feature (kept as a reporting/fairness dimension
  only): it is uncorrelated with every other feature and contributes zero
  out-of-fold AUC — its coefficient was amplifying a statistically
  non-significant gap measured on 29 female students.
- Count features now enter the model log-compressed (log1p) + robust-scaled.
- Sigmoid-calibrated probabilities: risk bands now read as real failure odds
  (out-of-fold, 84% of students above the High alert line actually failed).
- `scored_students.json` now holds **out-of-fold** probabilities, so the
  dashboard's historical evidence shows generalisation, not training fit.
- Fixed the engagement component weights, which never matched the Excel
  export's component names (`Assignment`, `File`, …) — both naming schemes
  (export + live DB) are now covered.
- Week-cutoff models (wk 2–10) ship in the model bundle; the live scorer picks
  the one matching the cohort's elapsed weeks, and neutralises features the
  course structurally lacks (zero across the whole cohort) to the training
  median — live demo cohort no longer over-flagged as ~all High.
- Fixed the live scorer reading Unix timestamps as UTC: night/weekend
  features now use local (server) time, matching training.
- Early-warning and the historical replay now use the same repeated
  out-of-fold protocol (replay previously scored students the model was
  trained on and flagged nearly the whole cohort every week; it now flags
  ~40% of the cohort at the High alert line, with precision rising
  0.68 → 0.81 across the term).
- Risk-band cutoffs are now derived from data at each retrain instead of the
  fixed 0.33/0.66 scale split: the High alert line is the highest threshold
  still catching ≥ 60% of actual failures out-of-fold — chosen just before
  the precision cliff (84% precision; the old fixed line caught only 47%) —
  and the Low line requires a historical failure rate of at most half the
  cohort's base rate.
- All models are strictly behavioral: continuous-assessment marks were
  trialled as week-cutoff features and removed the same day — a mark is a
  component of the final total that defines the at-risk label, so it leaked
  the answer into the prediction and inflated the early-warning numbers.
  Honest behavioral-only early warning, now reported for weeks 2–10:
  AUC 0.59 (week 2) → 0.71 (week 8) → 0.76 (week 10).

### Dashboard
- Engagement-vs-mark scatter: legend for the risk colours, dashed pass-mark
  line at 50, and a caption stating dots are out-of-sample predictions.
- Model page: accuracy, at-risk recall and High-band reliability KPIs plus
  the evaluation protocol note.
- Model page: early-warning bars sorted numerically (weeks 10/12 previously
  rendered before week 2).

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
