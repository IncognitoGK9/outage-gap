"""Count outage events at one site from raw sensor readings, by the rule used in the calibration.

Input, either of two CSV layouts:
  (a) raw readings: columns device, time, on_battery (1 if the sensor reported loss of mains power, else 0);
  (b) nLine GridWatch 30-minute bins: columns device, bin, n_obs, n_unpowered (a sensor is down when n_unpowered / n_obs >= 0.5).
Rule: a sensor is down in a 30-minute bin if at least half of its readings in that bin are on battery; a site event is a
run of bins with at least one sensor down, merged when two runs are 60 minutes apart or less; an event counts if
2 or more sensors saw it. Use the count 'events_2plus' as the input 'observed_events' of OutageGap.
Run: python -m outage_gap.count_events readings.csv
"""
import sys
import pandas as pd


def count_events(df, gap_min=60, min_sensors=2):
    df = df.copy()
    if "n_unpowered" in df.columns:
        df["bin"] = pd.to_datetime(df["bin"])
        per = df.assign(on_battery=df.n_unpowered / df.n_obs)[["device", "bin", "on_battery"]]
    else:
        df["bin"] = pd.to_datetime(df["time"]).dt.floor("30min")
        per = df.groupby(["device", "bin"]).on_battery.mean().reset_index()
    down = per[per.on_battery >= 0.5].groupby("bin").device.apply(set)
    events, cur, last = [], set(), None
    for b, s in down.sort_index().items():
        if last is not None and (b - last) > pd.Timedelta(minutes=gap_min):
            events.append(cur)
            cur = set()
        cur |= s
        last = b
    if last is not None:
        events.append(cur)
    sensors = df.device.nunique()
    two = sum(len(e) >= min_sensors for e in events)
    span = (df["bin"].max() - df["bin"].min()).days + 1
    reported = df.groupby("device").bin.nunique().mean() / max((span * 48), 1)
    return {"sensors": int(sensors), "events_2plus": int(two), "events_1_only": int(sum(len(e) == 1 for e in events)),
            "days": int(span), "uptime_estimate": round(float(reported), 3)}


if __name__ == "__main__":
    print(count_events(pd.read_csv(sys.argv[1])))
