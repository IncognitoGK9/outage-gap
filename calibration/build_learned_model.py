"""Train the learned estimator on synthetic worlds only, export it as plain JSON (no scikit-learn needed at run time), and
measure the log-error quantiles of its estimates on the real Accra draws (calibration/draws_clean.csv) for the 80% range.
Run from the repository root:  python3 calibration/build_learned_model.py"""
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from outage_gap.synthetic import FEATURES, SIZES, draw_worlds

S = draw_worlds(n_worlds=1500, seed=1)
S["o"] = np.maximum(S.obs, 1)
X = S[list(FEATURES)].to_numpy()
gb = GradientBoostingRegressor(n_estimators=250, max_depth=4, learning_rate=0.05, subsample=0.7, random_state=1)
gb.fit(X, np.log(S.full / S.o))

def export(gb):
    trees = []
    for e in gb.estimators_[:, 0]:
        t = e.tree_
        trees.append(dict(left=t.children_left.tolist(), right=t.children_right.tolist(), feature=t.feature.tolist(),
                          threshold=[round(float(v), 9) for v in t.threshold], value=[round(float(v[0][0]), 9) for v in t.value]))
    return dict(init=float(gb.init_.constant_[0][0]), learning_rate=float(gb.learning_rate), features=list(FEATURES), trees=trees)

real = pd.read_csv("calibration/draws_clean.csv")
real = real[real.full > 0].copy()
real["o"] = np.maximum(real.obs, 1)
real["chao"] = real.n1 ** 2 / (2 * real.n2 + 1)
real["pred"] = real.o * np.exp(gb.predict(real[list(FEATURES)].to_numpy()))
real["e"] = np.log(real.full / real.pred)
rng_q = {str(k): dict(mult_lo=round(float(np.exp(g.e.quantile(.1))), 4), mult_hi=round(float(np.exp(g.e.quantile(.9))), 4),
                      median_abs_err=round(float((np.abs(g.pred - g.full) / g.full).median()), 4)) for k, g in real.groupby("k") if k in SIZES}
out = dict(model=export(gb), ranges=rng_q, n_train_rows=int(len(S)), n_worlds=int(S.world.nunique()),
           source="gradient boosting trained on synthetic worlds only (domain randomization); ranges from errors on 2 real Accra sites (86 site-months)")
json.dump(out, open("outage_gap/learned_model.json", "w"), separators=(",", ":"))
print("trained on", len(S), "rows;", {k: v for k, v in rng_q.items()})
