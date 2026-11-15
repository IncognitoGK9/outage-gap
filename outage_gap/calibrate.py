"""Measure your own detection curve from dense sensor sites.

A dense site is a site with many sensors (the shipped curve used 15 to 23). Its full-site count of events seen by
2 or more sensors is the reference N. For each site-month, this function draws random subsets of k sensors, rebuilds
the events from the subset's own readings under the same 2-sensor rule, and records the share of N that the subset counted.
The result has the same layout as the shipped calibration.json, so it can be passed as `cal=` to
outage_gap.core.estimate() or posted to the API.

Input (a DataFrame or CSV): columns device, bin, n_obs, n_unpowered  OR  device, time, on_battery;
an optional `site` (or `site_id`) column names the site. See outage_gap.count_events.

Usage:  python -m outage_gap calibrate dense.csv -o my_curve.json
"""
import numpy as np
import pandas as pd
from .count_events import bins_table, build_events

DEFAULT_SIZES = (3, 4, 5, 6, 7, 8)
MIN_SITE_MONTHS = 6


def _share(d, a="obs_rb", b="full"):
    return d[a].sum() / d[b].sum()


def curve_from_draws(R, source, extra=None, estimate_sizes=None):
    """Turn a table of subset draws (columns site, month, k, full, obs1, obs2, obs_rb) into a calibration dictionary.

    c       = events a k-sensor site counts from its own readings / events seen by 2+ sensors of the full dense site.
    estimate_sizes: sizes that go into 'k' (the sizes the estimator accepts); every size goes into 'saturation'.
              Default: all sizes. The shipped curve uses 3 to 8 and keeps 12 and 16 for the saturation test only.
    range   = 10th and 90th percentile of the relative error when a share learned elsewhere is applied:
              to each site, the share from all OTHER sites (if there are 2 or more sites);
              with one site, the share from the other half of the months (earlier half / later half).
    """
    R = R[R.full > 0].copy()
    sites = sorted(R.site.unique())
    months = sorted(R.month.unique())
    half = set(months[: len(months) // 2])
    out = {"source": source, "k": {}, "saturation": {}}
    for k in sorted(R.k.unique()):
        d = R[R.k == k]
        c = _share(d)
        per_site = {s: _share(g) for s, g in d.groupby("site")}
        errs = []
        if len(sites) >= 2:
            for s in sites:
                t, other = d[d.site == s], d[d.site != s]
                if len(t) and len(other):
                    errs.append((t.obs_rb / _share(other) - t.full) / t.full)
        else:
            a, b = d[d.month.isin(half)], d[~d.month.isin(half)]
            for t, other in ((a, b), (b, a)):
                if len(t) and len(other):
                    errs.append((t.obs_rb / _share(other) - t.full) / t.full)
        e = pd.concat(errs) if errs else pd.Series([0.0])
        row = {"c": round(float(c), 4), "c_site_min": round(min(per_site.values()), 4),
               "c_site_max": round(max(per_site.values()), 4),
               "err_q10": round(float(e.quantile(.10)), 4), "err_q50": round(float(e.quantile(.50)), 4),
               "err_q90": round(float(e.quantile(.90)), 4), "median_abs_err": round(float(e.abs().median()), 4),
               "n_draws": int(len(d)), "c_any_one_sensor": round(float(_share(d, "obs1")), 4),
               "c_events_fixed_at_full_site": round(float(_share(d, "obs2")), 4)}
        if estimate_sizes is None or int(k) in estimate_sizes:
            out["k"][str(int(k))] = row
        out["saturation"][str(int(k))] = {"c": row["c"], "c_any_one_sensor": row["c_any_one_sensor"]}
    if extra:
        out.update(extra)
    return out


def draw_table(df, sizes=DEFAULT_SIZES, draws=40, seed=1, min_sensors=8, min_coverage=0.6, gap_min=60, min_seen=2):
    """The slow step: random subsets of each size in every usable site-month. Returns (table, info)."""
    if draws < 1:
        raise ValueError("draws must be at least 1.")
    if min_sensors < 3:
        raise ValueError("min_sensors must be at least 3.")
    per = bins_table(df)
    if per.empty:
        raise ValueError("The file has no readings.")
    per["down"] = per.on_battery >= 0.5
    per["month"] = per.bin.dt.to_period("M")
    rng = np.random.default_rng(seed)
    rows, covs, nsens = [], [], []
    for (s, m), g in per.groupby(["site", "month"]):
        cov = g.groupby("device").bin.nunique() / (g.bin.dt.days_in_month.iloc[0] * 48)
        devs = cov[cov >= min_coverage].index.tolist()
        if len(devs) < min_sensors:
            continue
        g = g[g.device.isin(devs)]
        dn = g[g.down].groupby("bin").device.apply(set)
        if dn.empty:
            continue
        items = list(dn.items())
        E = [x for x in build_events(items, gap_min) if len(x) >= min_seen]
        covs.append(float(cov[devs].mean()))
        nsens.append(len(devs))
        for k in sizes:
            if k > len(devs):
                continue
            for _ in range(draws):
                sub = set(rng.choice(devs, k, replace=False))
                fr = [len(e & sub) for e in E]
                rb = [x for x in build_events([(b, v & sub) for b, v in items if v & sub], gap_min) if len(x) >= min_seen]
                rows.append(dict(site=str(s), month=str(m), k=k, sensors_in_month=len(devs), full=len(E),
                                 obs2=sum(f >= min_seen for f in fr), obs1=sum(f > 0 for f in fr), obs_rb=len(rb)))
    return pd.DataFrame(rows), dict(covs=covs, nsens=nsens)


def calibrate(df, sizes=DEFAULT_SIZES, draws=40, seed=1, min_sensors=8, min_coverage=0.6, gap_min=60, min_seen=2):
    """Measure a detection curve from dense sites in `df`. Returns a calibration dictionary (JSON-ready).

    sizes        sensor counts to measure (each must be at most the number of usable sensors in some site-month)
    draws        random subsets per site-month and size (more draws, smoother curve, slower)
    min_sensors  a site-month is a dense reference only if at least this many sensors each reported in
                 min_coverage of its 30-minute bins
    """
    sizes = tuple(sorted({int(k) for k in sizes}))
    if not sizes or sizes[0] < 2:
        raise ValueError("sizes must be sensor counts of 2 or more.")
    R, info = draw_table(df, sizes, draws, seed, min_sensors, min_coverage, gap_min, min_seen)
    n_sm = R.groupby(["site", "month"]).ngroups if len(R) else 0
    if n_sm < MIN_SITE_MONTHS:
        raise ValueError(f"Only {n_sm} usable site-months found; at least {MIN_SITE_MONTHS} are needed. A usable site-month has "
                         f"at least {min_sensors} sensors that each reported in {min_coverage:.0%} of the month's 30-minute bins "
                         f"and at least one outage. Lower min_sensors or min_coverage, or give more data.")
    have = {int(k) for k in R.k.unique()}
    lost = [k for k in sizes if k not in have]
    sites = sorted(R.site.unique())
    first, last = R.month.min(), R.month.max()
    warns = []
    if lost:
        warns.append(f"Sizes {lost} were dropped: no dense site-month has that many sensors.")
    if n_sm < 24:
        warns.append(f"Only {n_sm} site-months: the range is rough. The shipped curve used 86.")
    if len(sites) < 2:
        warns.append("One dense site only: the error range comes from earlier versus later months, not from different sites. "
                     "It is probably too narrow for a different place.")
    med_sens = float(np.median(info["nsens"]))
    warns.append(f"Shares are measured against dense sites with a median of {med_sens:g} sensors; if the share is still rising "
                 "at your largest size, the real share is lower (upper bound).")
    extra = {"reference_uptime": round(float(np.median(info["covs"])), 3), "reference_sensors_median": med_sens,
             "n_site_months": int(n_sm), "n_sites": len(sites),
             "range_method": "other sites" if len(sites) >= 2 else "earlier versus later months",
             "settings": dict(sizes=list(sizes), draws=draws, seed=seed, min_sensors=min_sensors,
                              min_coverage=min_coverage, gap_min=gap_min, min_seen=min_seen),
             "warnings": warns}
    src = (f"your dense data: {len(sites)} site(s), {n_sm} site-months, {first} to {last}; "
           f"events seen by {min_seen}+ sensors, rebuilt from the sensors the site has")
    cal = curve_from_draws(R, src, extra)
    return cal
