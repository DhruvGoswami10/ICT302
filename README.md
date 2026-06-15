# Smart LMS Dashboard (ICT302)

Moodle-integrated learning analytics that show a Unit Coordinator how students
are engaging — and use machine learning to flag students at risk of failing
**while the term is still running**.

![status](https://img.shields.io/badge/status-working%20prototype-brightgreen)

## Highlights
- 📊 **Live dashboard** (Chart.js) — engagement, risk distribution, activity
  timeline, and a live student table that auto-refreshes.
- 🧠 **At-risk model** — scikit-learn logistic regression trained on a real
  historical cohort (no external AI API). Early-warning AUC ≈ 0.77 by week 6.
- 🧩 **Moodle plugin** (`report_smartdashboard`) — in-LMS view for the UC plus a
  weekly scheduled risk scan.
- 🔁 **Real-time** scoring every minute + a full weekly retrain.
- 🧪 **Simulation** of a whole teaching period for demos and validation.

## Quick links
- Dashboard: `http://<vm-ip>/`
- Moodle: `http://<vm-ip>:8081/`
- Full documentation: [PROJECT.md](docs/PROJECT.md)
- Change history: [changelog.md](changelog.md)

## Repository layout
```
ml/             scikit-learn engine (features, training, live scoring)
dashboard/      Flask API + static Chart.js dashboard (served by nginx)
moodle-plugin/  Moodle report plugin (report_smartdashboard)
simulation/     teaching-period simulation + historical replay
data/           anonymised historical exports (logs + results)
setup/          install & bootstrap scripts
```

## Run
```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python ml/train_model.py        # train
venv/bin/python ml/score_moodle.py       # score live cohort
venv/bin/python simulation/simulate_activity.py   # demo activity
```
See [PROJECT.md](docs/PROJECT.md) for the full environment setup, services and accounts.
