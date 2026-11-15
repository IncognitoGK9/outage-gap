"""Dummy (synthetic) sites with known truth, for trying the whole pipeline without real data.

All data here is invented by a simple generator. Nothing in it is a measurement of a real place.
  - two DENSE sites (16 sensors) in 'world A': use them to calibrate your own curve;
  - three SPARSE sites (3, 5 and 8 sensors) from the same world A: the own curve should work on them;
  - one SPARSE site (3 sensors) from a different 'world B' (same uptime, but mostly small outages): a site where a curve
    from world A is expected to be wrong, and where no warning appears: only a dense site near it can tell.
Every sparse site has a true count, the events seen by 2 or more of the 16 sensors of the site's world, which is the same
reference definition that the calibration uses. The sparse files contain only the sensors the sparse site has.

World model: outages start at random times, last from 30 minutes to several hours, and each outage reaches a random share
of the site's sensors (a few outages reach most sensors, many reach few). A sensor reports in a 30-minute bin with
probability equal to its uptime.
"""
import functools
import numpy as np
import pandas as pd
from .calibrate import calibrate
from .core import estimate
from .count_events import count_by_site, count_events

N_SENSORS = 16
WORLDS = {"A": dict(uptime=0.90, wide_share=0.45, outages_per_month=38),
          "B": dict(uptime=0.90, wide_share=0.05, outages_per_month=38)}


def make_site(site, world, n_sensors, months, seed, start="2023-01-01"):
    """One site of `n_sensors` sensors in nLine 30-minute-bin layout (device, bin, n_obs, n_unpowered, site)."""
    w, rng, frames = WORLDS[world], np.random.default_rng(seed), []
    for m in pd.period_range(start, periods=months, freq="M"):
        t0 = m.start_time
        n_bins = m.days_in_month * 48
        down = np.zeros((n_sensors, n_bins), bool)
        for _ in range(rng.poisson(w["outages_per_month"])):
            s = rng.integers(0, n_bins)
            d = 1 + int(rng.lognormal(np.log(3), 0.8))                  # median 3 bins = 90 minutes
            reach = rng.beta(8, 2) if rng.random() < w["wide_share"] else rng.beta(0.6, 2.7)
            down[rng.random(n_sensors) < reach, s:s + d] = True
        rep = rng.random((n_sensors, n_bins)) < w["uptime"]
        di, bi = np.nonzero(rep)
        frames.append(pd.DataFrame({"device": [f"{site}-s{i:02d}" for i in di],
                                    "bin": t0 + pd.to_timedelta(bi * 30, unit="m"),
                                    "n_obs": 20, "n_unpowered": np.where(down[di, bi], 20, 0), "site": site}))
    return pd.concat(frames, ignore_index=True)


def _truth(full, site, period="quarter"):
    """True events per period: events seen by 2+ of all the sensors of the site's world."""
    return {r["period"]: r["events_2plus"] for r in count_by_site(full, period)}


SPARSE_SPEC = [("DUMMY-sparse-3", "A", 3, 201), ("DUMMY-sparse-5", "A", 5, 202), ("DUMMY-sparse-8", "A", 8, 203),
               ("DUMMY-sparse-3-smalloutages", "B", 3, 204)]
DENSE_SITES = ("DUMMY-dense-1", "DUMMY-dense-2")


def _catalog():
    cat = [dict(site=s, role="dense", sensors=N_SENSORS, months=9, world="A", note="use to calibrate your own curve")
           for s in DENSE_SITES]
    for site, world, k, _ in SPARSE_SPEC:
        cat.append(dict(site=site, role="sparse", sensors=k, months=12, world=world,
                        note="same world as the dense dummy sites" if world == "A" else
                             "different world: same uptime, but most outages reach only one or two sensors; no warning can detect this from the counts"))
    return cat


@functools.lru_cache(maxsize=1)
def build():
    """Generate the dummy sites once. Returns dict with dense, sparse (DataFrames), truth (dict) and catalog (list)."""
    dense = pd.concat([make_site("DUMMY-dense-1", "A", N_SENSORS, 9, 101),
                       make_site("DUMMY-dense-2", "A", N_SENSORS, 9, 102)], ignore_index=True)
    sparse, truth = [], {}
    for site, world, k, seed in SPARSE_SPEC:
        full = make_site(site, world, N_SENSORS, 12, seed)
        keep = sorted(full.device.unique())[:k]
        sparse.append(full[full.device.isin(keep)])
        truth[site] = _truth(full, site)
    return dict(dense=dense, sparse=pd.concat(sparse, ignore_index=True), truth=truth, catalog=_catalog())


def catalog():
    """List of dummy sites. Static: does not generate any data."""
    return _catalog()


def site_file(site):
    """CSV text of one dummy site (the file a user would upload)."""
    b = build()
    for df in (b["dense"], b["sparse"]):
        if site in set(df.site):
            return df[df.site == site].to_csv(index=False)
    raise KeyError(site)


def all_dense_file():
    return build()["dense"].to_csv(index=False)


def all_sparse_file():
    return build()["sparse"].to_csv(index=False)


@functools.lru_cache(maxsize=1)
def own_curve():
    """Curve measured on the two dense dummy sites (20 draws per site-month and size, to keep it fast)."""
    return calibrate(build()["dense"], sizes=(3, 4, 5, 6, 7, 8), draws=20, seed=1, min_sensors=8)


@functools.lru_cache(maxsize=1)
def run():
    """Full pipeline on the dummy sites: count events from each sparse file, estimate with the shipped Accra curve and
    with the own curve, compare with the known truth."""
    b, cal = build(), own_curve()
    rows = []
    for r in count_by_site(b["sparse"], "quarter"):
        true = b["truth"][r["site"]][r["period"]]
        row = dict(site=r["site"], quarter=r["period"], sensors=r["sensors"], counted=r["events_2plus"], true=true,
                   uptime=r["uptime_estimate"])
        for tag, c in (("accra", None), ("own", cal)):
            e = estimate(r["sensors"], r["events_2plus"], r["uptime_estimate"], c)
            row[f"{tag}_estimate"] = e.estimated_total
            row[f"{tag}_error_pct"] = round(100 * (e.estimated_total - true) / true, 1)
            row[f"{tag}_in_range"] = e.range_80[0] <= true <= e.range_80[1]
        row["counted_error_pct"] = round(100 * (r["events_2plus"] - true) / true, 1)
        rows.append(row)
    t = pd.DataFrame(rows)
    summary = []
    for site, g in t.groupby("site"):
        summary.append(dict(site=site, mean_abs_error_pct_raw_count=round(g.counted_error_pct.abs().mean(), 1),
                            mean_abs_error_pct_accra_curve=round(g.accra_error_pct.abs().mean(), 1),
                            mean_abs_error_pct_own_curve=round(g.own_error_pct.abs().mean(), 1)))
    return dict(rows=rows, summary=summary, own_curve=cal, note=(
        "Synthetic data. 'accra' uses the shipped curve; 'own' uses a curve measured on the two dense dummy sites. "
        "The truth is known because the data was generated."))
