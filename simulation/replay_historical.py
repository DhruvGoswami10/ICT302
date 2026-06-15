"""
Week-by-week replay over the REAL historical cohort.

For each week of the teaching period it rebuilds engagement features using only
the data available up to that week, scores every student with the trained model,
and measures how well the early flags match the actual end-of-term failures.
This is the evidence that the tool detects at-risk students *early*.

Output: simulation/historical_replay.json  (consumed for reporting / the brief).
"""
import json
import sys
import numpy as np
import pandas as pd
import joblib

sys.path.insert(0, "/home/td05/ict302/ml")
import lms_features as L

MODEL = "/home/td05/ict302/ml/models/risk_model.joblib"
OUT = "/home/td05/ict302/simulation/historical_replay.json"


def main():
    logs = L.load_logs()
    res = L.load_results()
    start, end = L.teaching_window(logs)
    bundle = joblib.load(MODEL)
    model = bundle["model"]

    truth = res.set_index("sid")["at_risk"].to_dict()
    weekly = []
    for wk in range(2, 13):
        cutoff = start + pd.Timedelta(weeks=wk)
        feat = L.build_features(logs, cutoff=cutoff, start=start)
        if not len(feat):
            continue
        proba = model.predict_proba(L.to_matrix(feat))[:, 1]
        feat = feat.assign(risk=proba)
        flagged = feat[feat["risk"] >= 0.5]
        # precision: of those flagged High, how many actually failed
        hits = sum(truth.get(int(s), 0) for s in flagged["sid"])
        actual_fail = sum(truth.values())
        caught = sum(1 for s in flagged["sid"] if truth.get(int(s), 0) == 1)
        weekly.append({
            "week": wk,
            "students_active": int(len(feat)),
            "flagged": int(len(flagged)),
            "flagged_correct": int(hits),
            "precision": round(hits / max(1, len(flagged)), 3),
            "recall": round(caught / max(1, actual_fail), 3),
        })
        print(f"Week {wk:2d}: flagged {len(flagged):3d}  precision {weekly[-1]['precision']:.2f}  "
              f"recall {weekly[-1]['recall']:.2f}")

    json.dump({"teaching_start": str(start.date()), "weeks": weekly,
               "total_at_risk": int(sum(truth.values())),
               "cohort": int(len(truth))},
              open(OUT, "w"), indent=2)
    print("Saved", OUT)


if __name__ == "__main__":
    main()
