"""Builds calibration.json from the subsampling draws.
c      = events a k-sensor site counts from its OWN readings (2+ of its sensors, events rebuilt from the subset readings, column obs_rb)
         / events seen by 2+ sensors of the full dense site. This is what a real sparse site does, so the shipped counting script matches it.
range  = 10th and 90th percentile of the CROSS-SITE relative error: the factor learned at one dense site is applied
         to the other dense site, so the range includes the difference between sites, not only sampling noise.
Run: python3 -I build_calibration.py calibration_draws.csv calibration.json"""
import sys, json
import pandas as pd, numpy as np
R = pd.read_csv(sys.argv[1])
out = {"source": "Accra dense sites 3 and 4, 86 site-months, Jan 2021 - Jul 2024; counting rule: events seen by 2+ sensors, rebuilt from the sensors the site has",
       "k": {}, "saturation": {}}
share = lambda d, a="obs_rb", b="full": d[a].sum() / d[b].sum()
for k in sorted(R.k.unique()):
    d = R[R.k == k]
    c = share(d)
    per_site = {int(s): share(g) for s, g in d.groupby("site")}
    cross = []
    for s, o in ((3, 4), (4, 3)):
        t, co = d[d.site == s], share(d[d.site == o])
        if len(t) and len(d[d.site == o]):
            cross.append((t.obs_rb / co - t.full) / t.full)
    e = pd.concat(cross)
    row = {"c": round(float(c), 4), "c_site_min": round(min(per_site.values()), 4), "c_site_max": round(max(per_site.values()), 4),
           "err_q10": round(float(e.quantile(.10)), 4), "err_q50": round(float(e.quantile(.50)), 4),
           "err_q90": round(float(e.quantile(.90)), 4), "median_abs_err": round(float(e.abs().median()), 4),
           "n_draws": int(len(d)), "c_any_one_sensor": round(float(share(d, "obs1")), 4),
           "c_events_fixed_at_full_site": round(float(share(d, "obs2")), 4)}
    if 3 <= k <= 8:
        out["k"][str(k)] = row
    out["saturation"][str(k)] = {"c": row["c"], "c_any_one_sensor": row["c_any_one_sensor"]}
json.dump(out, open(sys.argv[2], "w"), indent=2); print(json.dumps(out, indent=2))
