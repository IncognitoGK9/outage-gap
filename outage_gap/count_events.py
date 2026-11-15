"""Count outage events at a site from raw sensor readings, by the rule used in the calibration.

Input, either of two CSV layouts (an optional `site` or `site_id` column splits the file into sites):
  (a) raw readings: columns device, time, on_battery (1 if the sensor reported loss of mains power, else 0);
  (b) nLine GridWatch 30-minute bins: columns device, bin, n_obs, n_unpowered (a sensor is down when n_unpowered / n_obs >= 0.5).
Rule: a sensor is down in a 30-minute bin if at least half of its readings in that bin are on battery; a site event is a
run of bins with at least one sensor down, merged when two runs are 60 minutes apart or less; an event counts if
2 or more sensors saw it. Use the count 'events_2plus' as the input 'observed_events' of OutageGap.
Run: python -m outage_gap.count_events readings.csv
"""
import sys
import pandas as pd

PERIODS = {"all": None, "month": "M", "quarter": "Q", "year": "Y"}


def bins_table(df):
    """One row per sensor per 30-minute bin: columns site, device, bin, on_battery (share of readings on battery)."""
    df = df.copy()
    if "site" not in df.columns:
        df["site"] = df["site_id"] if "site_id" in df.columns else "site1"
    if {"device", "bin", "n_obs", "n_unpowered"} <= set(df.columns):
        df["bin"] = pd.to_datetime(df["bin"])
        df["on_battery"] = df.n_unpowered / df.n_obs
        return df[["site", "device", "bin", "on_battery"]]
    if {"device", "time", "on_battery"} <= set(df.columns):
        df["bin"] = pd.to_datetime(df["time"]).dt.floor("30min")
        return df.groupby(["site", "device", "bin"]).on_battery.mean().reset_index()
    raise ValueError("Columns not recognised. Use device,time,on_battery (raw readings) or "
                     "device,bin,n_obs,n_unpowered (nLine 30-minute bins). An optional 'site' column splits sites.")


def build_events(items, gap_min=60):
    """items: list of (bin, set of sensors down). Returns one sensor set per event (runs merged when <= gap_min apart)."""
    events, cur, last = [], set(), None
    for b, s in sorted(items, key=lambda t: t[0]):
        if last is not None and (b - last) > pd.Timedelta(minutes=gap_min):
            events.append(cur)
            cur = set()
        cur |= s
        last = b
    if last is not None:
        events.append(cur)
    return events


def _count(per, gap_min, min_sensors):
    down = per[per.on_battery >= 0.5].groupby("bin").device.apply(set)
    events = build_events(list(down.items()), gap_min)
    sensors = per.device.nunique()
    two = sum(len(e) >= min_sensors for e in events)
    span = (per["bin"].max() - per["bin"].min()).days + 1
    reported = per.groupby("device").bin.nunique().mean() / max((span * 48), 1)
    return {"sensors": int(sensors), "events_2plus": int(two), "events_1_only": int(sum(len(e) == 1 for e in events)),
            "events_seen_by_2": int(sum(len(e) == 2 for e in events)), "events_seen_by_3": int(sum(len(e) == 3 for e in events)),
            "events_seen_by_4plus": int(sum(len(e) >= 4 for e in events)),
            "days": int(span), "uptime_estimate": round(float(reported), 3)}


def count_events(df, gap_min=60, min_sensors=2):
    """Count events for ONE site (a `site` column, if present, is ignored)."""
    return _count(bins_table(df), gap_min, min_sensors)


def count_by_site(df, period="all", gap_min=60, min_sensors=2):
    """Count events for every site (and period) in one table. Returns a list of dictionaries.

    period: 'all' (one row per site), 'month', 'quarter' or 'year'. Sensors and uptime are measured inside each period.
    """
    if period not in PERIODS:
        raise ValueError(f"period must be one of {sorted(PERIODS)}.")
    per = bins_table(df)
    if per.empty:
        raise ValueError("The file has no readings.")
    key = PERIODS[period]
    per["period"] = "all" if key is None else per.bin.dt.to_period(key).astype(str)
    rows = []
    for (site, p), g in per.groupby(["site", "period"]):
        r = _count(g, gap_min, min_sensors)
        rows.append(dict(site=str(site), period=p, **r))
    return rows


if __name__ == "__main__":
    print(count_events(pd.read_csv(sys.argv[1])))
