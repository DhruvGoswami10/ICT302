"""
Train the at-risk classifier on the historical ICT001 data and emit artifacts:
  models/risk_model.joblib      - trained pipeline (scaler + classifier)
  models/metrics.json           - cross-validated model comparison + chosen model
  models/feature_importances.json
  models/scored_students.json   - per-student engagement + risk on the historical cohort
  models/early_warning.json     - AUC of predicting the final outcome from week-2/4/6/8 data

Pure scikit-learn (algorithm-based, no external AI API).
"""
import json
import os
import numpy as np
import pandas as pd
import joblib

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score, classification_report

import lms_features as L

OUT = "/home/td05/ict302/ml/models"
os.makedirs(OUT, exist_ok=True)


def make_models():
    return {
        "logistic": Pipeline([("sc", StandardScaler()),
                              ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))]),
        "random_forest": Pipeline([("sc", StandardScaler()),
                              ("clf", RandomForestClassifier(n_estimators=300, max_depth=6,
                                                             class_weight="balanced", random_state=42))]),
        "grad_boost": Pipeline([("sc", StandardScaler()),
                              ("clf", GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                                                 learning_rate=0.05, random_state=42))]),
    }


def main():
    logs = L.load_logs()
    res = L.load_results()
    start, end = L.teaching_window(logs)

    feat = L.build_features(logs, start=start)
    data = feat.merge(res, on="sid", how="inner")
    X = L.to_matrix(data)
    y = data["at_risk"].values
    print(f"Training on {len(data)} students, {y.mean()*100:.1f}% at-risk")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    metrics = {}
    best_name, best_auc = None, -1
    for name, model in make_models().items():
        proba = cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1]
        pred = (proba >= 0.5).astype(int)
        auc = roc_auc_score(y, proba)
        metrics[name] = {
            "roc_auc": round(float(auc), 4),
            "f1": round(float(f1_score(y, pred)), 4),
            "accuracy": round(float(accuracy_score(y, pred)), 4),
        }
        print(f"  {name:14s} AUC={auc:.3f} F1={metrics[name]['f1']:.3f} acc={metrics[name]['accuracy']:.3f}")
        if auc > best_auc:
            best_auc, best_name = auc, name

    print(f"Best model: {best_name} (AUC={best_auc:.3f})")
    final = make_models()[best_name]
    final.fit(X, y)
    joblib.dump({"model": final, "features": L.FEATURE_COLS,
                 "start": str(start), "end": str(end)}, f"{OUT}/risk_model.joblib")

    # feature importances / coefficients for explainability
    clf = final.named_steps["clf"]
    if hasattr(clf, "feature_importances_"):
        imp = dict(zip(L.FEATURE_COLS, [round(float(v), 4) for v in clf.feature_importances_]))
    else:
        imp = dict(zip(L.FEATURE_COLS, [round(float(v), 4) for v in clf.coef_[0]]))
    imp = dict(sorted(imp.items(), key=lambda kv: -abs(kv[1])))

    # in-sample scored cohort (with engagement index)
    eng = L.engagement_score(feat)
    feat2 = feat.copy(); feat2["engagement"] = eng
    full = feat2.merge(res, on="sid", how="left")
    proba_all = final.predict_proba(L.to_matrix(feat2))[:, 1]
    full["risk_prob"] = np.round(proba_all, 4)
    full["risk_band"] = pd.cut(full["risk_prob"], [-0.01, 0.33, 0.66, 1.01],
                               labels=["Low", "Medium", "High"]).astype(str)
    scored = full[["sid", "gender", "engagement", "total_events", "active_weeks",
                   "assign_events", "forum_events", "grade_checks",
                   "risk_prob", "risk_band", "mark", "grade", "at_risk"]].sort_values("risk_prob", ascending=False)
    scored.to_json(f"{OUT}/scored_students.json", orient="records")

    # early-warning: predict final outcome using only weeks 2/4/6/8 of data
    ew = {}
    Xtr_idx, Xte_idx = train_test_split(np.arange(len(data)), test_size=0.3,
                                        stratify=y, random_state=42)
    weeks = {2: start + pd.Timedelta(weeks=2), 4: start + pd.Timedelta(weeks=4),
             6: start + pd.Timedelta(weeks=6), 8: start + pd.Timedelta(weeks=8)}
    for wk, cutoff in weeks.items():
        fz = L.build_features(logs, cutoff=cutoff, start=start).merge(res, on="sid", how="inner")
        fz = fz.set_index("sid").reindex(data["sid"]).reset_index()
        Xz = L.to_matrix(fz.fillna(0)); yz = data["at_risk"].values
        m = make_models()[best_name]
        m.fit(Xz.iloc[Xtr_idx], yz[Xtr_idx])
        p = m.predict_proba(Xz.iloc[Xte_idx])[:, 1]
        ew[f"week_{wk}"] = round(float(roc_auc_score(yz[Xte_idx], p)), 4)
        print(f"  early-warning week {wk}: AUC={ew[f'week_{wk}']:.3f}")

    json.dump({"models": metrics, "chosen": best_name, "n_students": int(len(data)),
               "at_risk_rate": round(float(y.mean()), 4)},
              open(f"{OUT}/metrics.json", "w"), indent=2)
    json.dump(imp, open(f"{OUT}/feature_importances.json", "w"), indent=2)
    json.dump(ew, open(f"{OUT}/early_warning.json", "w"), indent=2)
    print("Artifacts written to", OUT)


if __name__ == "__main__":
    main()
