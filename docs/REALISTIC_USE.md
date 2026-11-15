# Using OutageGap in practice

## Who can use it
- **Regulators and ministries** that have a few plug-in sensor sites and need a fair outage count per district, but cannot afford sensors at every transformer.
- **Utilities and programme teams** (for example, evaluation teams of grid projects) that report SAIFI from sensor counts.
- **Researchers** who need to know how much a three-sensor design under-counts before they publish an index.

## What you need
1. Sensor records per site with a timestamp and an on-battery flag (or any power-on/power-off report).
2. A count of events per site and period, made with the same rule as the paper (see README). `python -m outage_gap count` or `analyze` does this from a raw file.
3. The sensor count per site, and if you can, the share of time the sensors reported (uptime).
4. A laptop or phone with a browser. The CSV tool (`python -m outage_gap`) needs only Python and works without internet after installation.

## A realistic workflow
1. **Count** events per site and month with the paper's rule.
2. **Check uptime.** If it is below 0.65 at many sites, do not trust the curve; fix the sensors first.
3. **Run `analyze`** on all sparse sites at once (or the CSV tool if you already have counts). Review the `warnings` column.
4. **Report quarters or years**, not single months, and report the 80% range next to the corrected count.
5. **Say what the number is**: a corrected count of outages that two or more sensors would have seen, not a utility record.

## Recalibrating for a new city (about ten minutes of work)
The shipped curve was measured in Accra. A new city needs its own dense reference: sites with 8 or more sensors (15 or more is better), for at least 6 site-months (24 or more is better), preferably two or more sites.
1. Put the dense sites' sensor records in one CSV (`device, bin, n_obs, n_unpowered`, or `device, time, on_battery`, plus an optional `site` column).
2. Measure the curve: `python -m outage_gap calibrate dense_sites.csv -o my_curve.json` (or tab 2 of the web app, or `POST /calibrate`).
3. Read the notes it prints. Compare the shares with Accra's 0.37 (3 sensors), 0.47 (5) and 0.62 (8). If they differ, the Accra curve was wrong for your city and yours is the one to use.
4. Use it everywhere: `python -m outage_gap analyze sparse_sites.csv --curve my_curve.json`.
To practise first, use the dummy sites: `python -m outage_gap demo --out dummy/`.

## What it cannot do
- It cannot find outages that no sensor saw, or transformers with no sensor.
- It does not correct outage duration (SAIDI).
- It is not a substitute for a utility outage record where one exists. Use it where the sensors are the only low-voltage record.
- It did not transfer to Sierra Leone in a preliminary check (6 site-months), so it must be recalibrated outside Accra.

## Practical limits in low-resource settings
- Data bundles and power cuts: use the offline CSV tool, and keep the Streamlit app for demonstrations.
- Staff time: counting events from raw device files is the hard step, not the estimate. `python -m outage_gap.count_events` applies the counting rule to a CSV with `device, time, on_battery`; it was checked on the real nLine bin files of the two dense Accra sites (full-site count equal to the reference in all 86 site-months), but not on exports from other deployments, so check it on one site by hand first.
- Trust: always show the range and the warnings, never a single number. Every output says: not a utility record. Do not rank districts with a single month's estimate: at three sensors the typical single-month error is about 44%.
