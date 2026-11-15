"""Synthetic sites used to train the learned estimator. Everything here is invented by a simple generator: nothing is a measurement.

A world has n sensors, a sensor uptime, an outage rate, a typical outage length and a share of wide outages (outages that reach most
sensors). The truth for a world-month is the number of events seen by 2 or more of its sensors, the same reference as the real Accra sites.
"""
import numpy as np
import pandas as pd

SIZES = (3, 4, 5, 6, 7, 8)
FEATURES = ("k", "n1", "n2", "n3", "n4p", "uptime", "chao")


def events_from(D):
    """D: bool matrix (sensors x 30-minute bins), True where a sensor is down. Returns, for each event, how many sensors saw it.
    Event rule: runs of bins with any sensor down, merged when 60 minutes apart or less (a gap of 2 bins or fewer)."""
    idx = np.flatnonzero(D.any(0))
    if idx.size == 0:
        return np.array([], int)
    starts = np.r_[0, np.flatnonzero(np.diff(idx) > 2) + 1]
    return (np.add.reduceat(D[:, idx].astype(np.int8), starts, axis=1) > 0).sum(0)


def world_month(n, n_bins, uptime, wide, rate, dur_med, rng):
    """One month of one world. Returns (down, reporting) boolean matrices; down is only seen where the sensor reports."""
    down = np.zeros((n, n_bins), bool)
    for _ in range(rng.poisson(rate)):
        s = rng.integers(0, n_bins)
        length = 1 + int(rng.lognormal(np.log(dur_med), 0.8))
        reach = rng.beta(8, 2) if rng.random() < wide else rng.beta(0.6, 2.7)
        down[rng.random(n) < reach, s:s + length] = True
    rep = rng.random((n, n_bins)) < uptime
    return down & rep, rep


def feature_row(seen, uptime, k):
    """Features of a sparse site from the number of its own sensors that saw each event (`seen`) and its uptime."""
    seen = np.asarray(seen)
    n1, n2, n3, n4p = (int((seen == 1).sum()), int((seen == 2).sum()), int((seen == 3).sum()), int((seen >= 4).sum()))
    return dict(k=k, n1=n1, n2=n2, n3=n3, n4p=n4p, uptime=float(uptime), chao=n1 * n1 / (2 * n2 + 1), obs=n2 + n3 + n4p)


def draw_worlds(n_worlds=1500, seed=1, draws=8, sizes=SIZES, n_range=(12, 20)):
    """Training table: for random worlds, random sensor subsets, their features and the true count (`full`)."""
    rng = np.random.default_rng(seed)
    rows = []
    for w in range(n_worlds):
        n = int(rng.integers(n_range[0], n_range[1] + 1))
        uptime, wide, rate, dur = rng.uniform(.55, .97), rng.uniform(0, .6), rng.uniform(15, 70), rng.uniform(1.5, 6)
        D, R = world_month(n, 30 * 48, uptime, wide, rate, dur, rng)
        full = int((events_from(D) >= 2).sum())
        if full == 0:
            continue
        for k in sizes:
            for _ in range(draws):
                sub = rng.choice(n, k, replace=False)
                rows.append(dict(world=w, full=full, **feature_row(events_from(D[sub]), R[sub].mean(), k)))
    return pd.DataFrame(rows)
