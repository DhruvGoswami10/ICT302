"""Train the at-risk classifier on the historical ICT001 data (scikit-learn only).
Writes to models/: risk_model.joblib, metrics.json, feature_importances.json,
scored_students.json, early_warning.json.
Every reported metric and per-student probability is out-of-fold (stratified
5-fold CV repeated over CV_SEEDS); probabilities are sigmoid-calibrated."""
import json
import os
import numpy as np
import pandas as pd
import joblib

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score, recall_score

import lms_features as L

OUT = "/home/td05/ict302/ml/models"
os.makedirs(OUT, exist_ok=True)

CV_SEEDS = [0, 1, 2, 3, 4]
BAND_LABELS = ["Low", "Medium", "High"]
HIGH_RECALL_TARGET = 0.60  # the High band must catch >= this share of actual failures


def derive_bands(proba, y):
    """Derive band cutoffs from out-of-fold probabilities.
    High: highest threshold still catching HIGH_RECALL_TARGET of actual failures
    (UC prefers false positives over missed students).
    Low: highest threshold whose band failed at <= half the base rate, else empty.
    Cutoffs sit half a rounding step lower so the boundary student stays in-band."""
    p = np.round(proba, 4)
    fails = max(1, int(y.sum()))
    high = 0.5  # fall back to the model's decision point
    for t in np.sort(np.unique(p))[::-1]:
        if y[p >= t].sum() / fails >= HIGH_RECALL_TARGET:
            high = float(t)
            break
    low = float(np.min(p))
    for t in np.sort(np.unique(p))[::-1]:
        m = p < t
        if t < high and m.any() and y[m].mean() <= y.mean() / 2:
            low = float(t)
            break
    return round(low - 0.00005, 5), round(high - 0.00005, 5)


def make_models():
    # RobustScaler: counts stay heavy-tailed after log1p, medians/IQR are stabler at n=168
    logistic = Pipeline([("sc", RobustScaler()),
                         ("clf", LogisticRegression(max_iter=5000, class_weight="balanced"))])
    forest = Pipeline([("sc", RobustScaler()),
                       ("clf", RandomForestClassifier(n_estimators=300, max_depth=6,
                                                      class_weight="balanced", random_state=42))])
    boost = Pipeline([("sc", RobustScaler()),
                      ("clf", GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                                         learning_rate=0.05, random_state=42))])
    # sigmoid calibration so predicted probabilities match observed failure rates
    return {
        "logistic": CalibratedClassifierCV(logistic, method="sigmoid", cv=5),
        "random_forest": CalibratedClassifierCV(forest, method="sigmoid", cv=5),
        "grad_boost": CalibratedClassifierCV(boost, method="sigmoid", cv=5),
    }


def oof_proba(model, X, y, seed):
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    return cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1]


def main():
    logs = L.load_logs()
    res = L.load_results()
    start, end = L.teaching_window(logs)

    feat = L.build_features(logs, start=start, end=end)
    data = feat.merge(res, on="sid", how="inner")
    X = L.to_matrix(data)
    y = data["at_risk"].values
    print(f"Training on {len(data)} students, {y.mean()*100:.1f}% at-risk")

    metrics = {}
    best_name, best_auc = None, -1
    proba_by_model = {}
    for name, model in make_models().items():
        seed_probas = [oof_proba(model, X, y, s) for s in CV_SEEDS]
        per = {"roc_auc": [], "f1": [], "accuracy": [], "recall": []}
        for p in seed_probas:
            pred = (p >= 0.5).astype(int)
            per["roc_auc"].append(roc_auc_score(y, p))
            per["f1"].append(f1_score(y, pred))
            per["accuracy"].append(accuracy_score(y, pred))
            per["recall"].append(recall_score(y, pred))
        metrics[name] = {k: round(float(np.mean(v)), 4) for k, v in per.items()}
        proba_by_model[name] = np.mean(seed_probas, axis=0)
        print(f"  {name:14s} AUC={metrics[name]['roc_auc']:.3f} F1={metrics[name]['f1']:.3f} "
              f"acc={metrics[name]['accuracy']:.3f}  ({len(CV_SEEDS)}x5-fold OOF)")
        if metrics[name]["roc_auc"] > best_auc:
            best_auc, best_name = metrics[name]["roc_auc"], name

    print(f"Best model: {best_name} (AUC={best_auc:.3f})")
    final = make_models()[best_name]
    final.fit(X, y)

    # coefficients for explainability, from the uncalibrated pipeline
    # (the calibration wrapper preserves the ranking, only rescales probabilities)
    expl = Pipeline([("sc", RobustScaler()),
                     ("clf", LogisticRegression(max_iter=5000, class_weight="balanced"))]).fit(X, y)
    imp = dict(zip(L.FEATURE_COLS,
                   [round(float(v), 4) for v in expl.named_steps["clf"].coef_[0]]))
    imp = dict(sorted(imp.items(), key=lambda kv: -abs(kv[1])))

    # dashboard cohort scores are OOF probabilities averaged over the CV shuffles
    eng = L.engagement_score(feat)
    feat2 = feat.copy(); feat2["engagement"] = eng
    full = feat2.merge(res, on="sid", how="left")
    oof = pd.Series(proba_by_model[best_name], index=data["sid"].values)
    full["risk_prob"] = full["sid"].map(oof)
    missing = full["risk_prob"].isna()
    if missing.any():  # students absent from the results file: score with the fitted model
        full.loc[missing, "risk_prob"] = final.predict_proba(
            L.to_matrix(feat2[missing.values]))[:, 1]
    full["risk_prob"] = full["risk_prob"].round(4)

    low_cut, high_cut = derive_bands(proba_by_model[best_name], y)
    bands = [-0.01, low_cut, high_cut, 1.01]
    print(f"Band cutoffs derived from data: low<{low_cut} high>={high_cut} "
          f"(High catches >= {HIGH_RECALL_TARGET:.0%} of actual failures out-of-fold)")
    full["risk_band"] = pd.cut(full["risk_prob"], bands, labels=BAND_LABELS).astype(str)
    scored = full[["sid", "gender", "engagement", "total_events", "active_weeks",
                   "assign_events", "forum_events", "grade_checks",
                   "risk_prob", "risk_band", "mark", "grade", "at_risk"]].sort_values("risk_prob", ascending=False)
    scored.to_json(f"{OUT}/scored_students.json", orient="records")

    # observed failure rate per band (OOF)
    band = pd.cut(proba_by_model[best_name], bands, labels=BAND_LABELS)
    alignment = {}
    for b in BAND_LABELS:
        m = np.asarray(band == b)
        alignment[b.lower()] = {"students": int(m.sum()),
                                "actually_failed": round(float(y[m].mean()), 4) if m.any() else None}
    n_fails = max(1, int(y.sum()))
    alignment["high"]["share_of_failures_caught"] = round(
        float(y[np.asarray(band == "High")].sum() / n_fails), 4)
    print("Band alignment (OOF):", alignment)

    # early-warning: same repeated OOF protocol, data up to each week cutoff only.
    # A model fitted per cutoff also ships: a mid-term cohort must be scored by a
    # model with a matching data window, or everyone looks disengaged against
    # full-term feature ranges and gets over-flagged.
    ew = {}
    week_models = {}
    yz = data["at_risk"].values
    for wk in (2, 4, 6, 8, 10):
        cutoff = start + pd.Timedelta(weeks=wk)
        fz = L.build_features(logs, cutoff=cutoff, start=start).merge(res, on="sid", how="inner")
        fz = fz.set_index("sid").reindex(data["sid"]).reset_index()
        Xz = L.to_matrix(fz.fillna(0))
        m = make_models()[best_name]
        aucs = [roc_auc_score(yz, oof_proba(m, Xz, yz, s)) for s in CV_SEEDS]
        ew[f"week_{wk}"] = round(float(np.mean(aucs)), 4)
        print(f"  early-warning week {wk}: AUC={ew[f'week_{wk}']:.3f}")
        wm = make_models()[best_name]
        wm.fit(Xz, yz)
        week_models[wk] = {"model": wm, "features": L.FEATURE_COLS,
                           "medians": {c: float(Xz[c].median()) for c in L.FEATURE_COLS}}

    joblib.dump({"model": final, "week_models": week_models, "features": L.FEATURE_COLS,
                 # live scorer uses these to neutralise features a course doesn't offer
                 "feature_medians": {c: float(X[c].median()) for c in L.FEATURE_COLS},
                 "bands": {"low": low_cut, "high": high_cut},
                 "start": str(start), "end": str(end)}, f"{OUT}/risk_model.joblib")

    json.dump({"models": metrics, "chosen": best_name, "n_students": int(len(data)),
               "at_risk_rate": round(float(y.mean()), 4),
               "protocol": f"{len(CV_SEEDS)}x repeated stratified 5-fold CV, all metrics out-of-fold",
               "risk_bands": {"low": low_cut, "high": high_cut,
                              "high_recall_target": HIGH_RECALL_TARGET},
               "band_alignment": alignment},
              open(f"{OUT}/metrics.json", "w"), indent=2)
    json.dump(imp, open(f"{OUT}/feature_importances.json", "w"), indent=2)
    json.dump(ew, open(f"{OUT}/early_warning.json", "w"), indent=2)
    print("Artifacts written to", OUT)


if __name__ == "__main__":
    main()
