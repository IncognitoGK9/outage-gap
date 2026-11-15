"""Plain-English explanations of every result, for readers who are not technical.

Each function returns short text built only from the numbers of the result. Nothing here changes any number.
"""
from .core import sizes_of


def _n(x):
    return f"{x:,.0f}"


def explain_estimate(r):
    """r: Estimate (or the dict from asdict). Returns dict(headline, steps, how_sure, advice)."""
    g = (lambda k: getattr(r, k)) if not isinstance(r, dict) else r.__getitem__
    k, seen, share = g("sensors"), g("observed_events"), g("detection_share")
    tot, missed, (lo, hi) = g("estimated_total"), g("estimated_missed"), g("range_80")
    per100 = round(100 * share)
    headline = (f"Your site with {k} sensors counted {seen} outages. We think the real number is about {_n(tot)}, "
                f"so about {_n(missed)} were missed.")
    steps = [
        f"A site with {k} sensors usually counts only about {per100} of every 100 outages that a full group of sensors would count.",
        f"So we divide your count ({seen}) by {share:.2f}. That gives about {_n(tot)}.",
        f"We are fairly sure (80 in 100 times) that the real number lies between {_n(lo)} and {_n(hi)}.",
    ]
    ratio = hi / lo if lo > 0 else float("inf")
    if seen == 0:
        how = "With no outages counted we cannot say much. Use a longer period."
    elif ratio <= 2.5:
        how = "The range is fairly narrow, so you can use the estimate with some confidence."
    elif ratio <= 4.5:
        how = "The range is wide. Use the estimate as a rough size, not as an exact number."
    else:
        how = ("The range is very wide. This is because a site with few sensors misses a lot and the miss rate changes "
               "from month to month. Treat the answer as 'somewhere between low and high', and prefer a longer period or more sensors.")
    advice = ("Counts for one month are noisy. Add several months together for a steadier answer." if seen < 30 else
              "The count is large enough that the range mostly reflects the sensors, not chance.")
    return dict(headline=headline, steps=steps, how_sure=how, advice=advice)


def explain_curve(cv):
    """cv: a calibration dict (from calibrate()). Returns dict(headline, lines, how_sure)."""
    sizes = sizes_of(cv)
    lines = []
    for k in sizes:
        p = cv["k"][str(k)]
        lines.append(f"{k} sensors: counts about {round(100 * p['c'])} of every 100 outages. "
                     f"A single month is typically off by about {round(100 * p['median_abs_err'])}%.")
    n, m = cv.get("n_sites"), cv.get("n_site_months")
    head = (f"Your curve was measured on {n} dense site(s), {m} site-months. It says how much of the outage count a small "
            f"group of sensors keeps, for each group size from {sizes[0]} to {sizes[-1]}.")
    how = ("A curve from one or two sites may not fit other places. It is most reliable for sites that look like the ones it was measured on."
           if (n or 0) < 4 else "The curve comes from several sites, so it is more likely to fit similar places.")
    if cv.get("warnings"):
        how += " Read the notes below: they say where the curve may fail."
    return dict(headline=head, lines=lines, how_sure=how)


def explain_plan(p):
    t = p["target_share"]
    if p["sensors_needed"]:
        s = (f"To count at least {round(100 * t)} of every 100 outages, a site needs about {p['sensors_needed']} sensors. "
             "This is the best case: the real share is lower, because the dense reference sites also miss some outages.")
    else:
        s = (f"No tested group size reaches {round(100 * t)} of every 100 outages. "
             "More sensors than we measured would be needed, or the target is too high.")
    return dict(headline=s, how_sure="Each extra sensor helps less than the one before it, so adding sensors has a point of low return.")


def explain_demo(res):
    """res: output of demo.run(). Says in words who won on each dummy site."""
    out = []
    for s in res["summary"]:
        raw, ac, own = (s["mean_abs_error_pct_raw_count"], s["mean_abs_error_pct_accra_curve"], s["mean_abs_error_pct_own_curve"])
        best = min(("raw count", raw), ("Accra curve", ac), ("own curve", own), key=lambda x: x[1])
        out.append(f"{s['site']}: just using the count is off by {raw:.0f}% on average; the Accra curve by {ac:.0f}%; "
                   f"the curve you measured by {own:.0f}%. Closest: {best[0]}.")
    return dict(
        headline="This test uses invented sites where the true number of outages is known, so we can check each method.",
        lines=out,
        how_sure=("Where the own curve wins, measuring your own curve helps. The site named 'smalloutages' is a warning: "
                  "there the own curve is wrong and nothing in the counts shows it (the Accra curve looks best there by chance). Check your curve against dense sites "
                  "that look like the place you want to estimate."))
