"""
Week-by-week replay over the REAL historical cohort.

For each week of the teaching period it rebuilds engagement features using only
the data available up to that week and scores every student OUT-OF-FOLD (the
scoring model never saw that student), then measures how well the early flags
match the actual end-of-term failures. This is the evidence that the tool
detects at-risk students *early*, without the optimism of scoring students the
model was trained on.

Output: simulation/historical_replay.json  (consumed for reporting / the brief).
"""
import json
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/td05/ict302/ml")
import lms_features as L
from train_model import make_models, oof_proba, CV_SEEDS

MODELS = "/home/td05/ict302/ml/models"
OUT = "/home/td05/ict302/simulation/historical_replay.json"


def main():
    logs = L.load_logs()
    res = L.load_results()
    start, end = L.teaching_window(logs)
    chosen = json.load(open(f"{MODELS}/metrics.json"))["chosen"]

    truth = res.set_index("sid")["at_risk"].to_dict()
    weekly = []
    for wk in range(2, 13):
        cutoff = start + pd.Timedelta(weeks=wk)
        feat = L.build_features(logs, cutoff=cutoff, start=start)
        if not len(feat):
            continue
        fz = feat.merge(res, on="sid", how="inner")
        Xz = L.to_matrix(fz)
        yz = fz["at_risk"].values
        proba = np.mean([oof_proba(make_models()[chosen], Xz, yz, s)
                         for s in CV_SEEDS], axis=0)
        fz = fz.assign(risk=proba)
        flagged = fz[fz["risk"] >= 0.5]
        # precision: of those flagged, how many actually failed
        hits = int(flagged["at_risk"].sum())
        actual_fail = sum(truth.values())
        weekly.append({
            "week": wk,
            "students_active": int(len(feat)),
            "flagged": int(len(flagged)),
            "flagged_correct": hits,
            "precision": round(hits / max(1, len(flagged)), 3),
            "recall": round(hits / max(1, actual_fail), 3),
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
