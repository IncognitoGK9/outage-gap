"""Rebuild calibration_draws.csv from nLine GridWatch device files of the two dense Accra sites.

Input: CSV with columns device, bin, n_obs, n_unpowered, site_id (one row per sensor per 30-minute bin) for
site_id 3 and 4 (see extract_sites.py).
Usage: python3 -I run_subsampling.py sites34.csv ../calibration/calibration_draws.csv

Columns written (one row per random subset of k sensors in one site-month):
  full      N: events seen by 2 or more sensors of the full set (the reference count)
  obs2      events of N that 2 or more subset sensors saw   <- the PowerWatch counting rule (used by the app)
  obs1      events of N that at least 1 subset sensor saw   (needed by Chao2, which uses events seen once)
  chao      Chao2 estimate from the subset (uses obs1 and the numbers of events seen once and twice)
  full3     events seen by 3 or more sensors of the full set (stricter reference, sensitivity test)
  obs2_f3   events of full3 that 2 or more subset sensors saw
  obs_rb    events counted when the site rebuilds its events from the subset readings alone (>=2 subset sensors)
"""
import sys
import numpy as np
import pandas as pd

SEED, DRAWS = 1, 40
SIZES = (3, 4, 5, 6, 7, 8, 12, 16)
MIN_SENSORS, MIN_COVERAGE, GAP_MIN, MIN_SEEN = 8, 0.6, 60, 2


def chao2(freqs, T):
    q1 = sum(f == 1 for f in freqs)
    q2 = sum(f == 2 for f in freqs)
    return ((T - 1) / T) * (q1 * q1 / (2 * q2) if q2 > 0 else q1 * (q1 - 1) / 2)


def build_events(items):
    """items: list of (bin, set of sensors down). Returns list of sensor sets, one per event (60-minute merge)."""
    items = sorted(items, key=lambda t: t[0])
    ev, cur, last = [], set(), None
    for b, s in items:
        if last is not None and (b - last) > pd.Timedelta(minutes=GAP_MIN):
            ev.append(cur)
            cur = set()
        cur |= s
        last = b
    if last is not None:
        ev.append(cur)
    return ev


def main(src, dst):
    rng = np.random.default_rng(SEED)
    d = pd.read_csv(src, usecols=["device", "bin", "n_obs", "n_unpowered", "site_id"], parse_dates=["bin"])
    d["down"] = d.n_unpowered / d.n_obs >= 0.5
    d["month"] = d.bin.dt.to_period("M")
    rows = []
    for (s, m), g in d.groupby(["site_id", "month"]):
        cov = g.groupby("device").bin.nunique() / (g.bin.dt.days_in_month.iloc[0] * 48)
        devs = cov[cov >= MIN_COVERAGE].index.tolist()
        if len(devs) < MIN_SENSORS:
            continue
        g = g[g.device.isin(devs)]
        dn = g[g.down].groupby("bin").device.apply(set)
        if dn.empty:
            continue
        items = list(dn.items())
        E = [x for x in build_events(items) if len(x) >= MIN_SEEN]
        E3 = [x for x in E if len(x) >= 3]
        full, full3 = len(E), len(E3)
        for k in SIZES:
            if k > len(devs):
                continue
            for _ in range(DRAWS):
                sub = set(rng.choice(devs, k, replace=False))
                fr = [len(e & sub) for e in E]
                seen = [f for f in fr if f > 0]
                rb = [x for x in build_events([(b, v & sub) for b, v in items if v & sub]) if len(x) >= MIN_SEEN]
                rows.append(dict(site=s, month=str(m), k=k, sensors_in_month=len(devs), full=full,
                                 obs2=sum(f >= 2 for f in fr), obs1=len(seen), chao=len(seen) + chao2(seen, k),
                                 full3=full3, obs2_f3=sum(len(e & sub) >= 2 for e in E3), obs_rb=len(rb)))
    R = pd.DataFrame(rows)
    R.to_csv(dst, index=False)
    print("site-months:", R.groupby(["site", "month"]).ngroups)
    for col in ("obs2", "obs1", "obs_rb"):
        print(col, "share of N:", (R.groupby("k")[col].sum() / R.groupby("k").full.sum()).round(3).to_dict())
    print("obs2_f3 share of full3:", (R.groupby("k").obs2_f3.sum() / R.groupby("k").full3.sum()).round(3).to_dict())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
