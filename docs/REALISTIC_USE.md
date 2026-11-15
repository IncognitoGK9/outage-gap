# Using OutageGap in practice

## Who can use it
- **Regulators and ministries** that have a few plug-in sensor sites and need a fair outage count per district, but cannot afford sensors at every transformer.
- **Utilities and programme teams** (for example, evaluation teams of grid projects) that report SAIFI from sensor counts.
- **Researchers** who need to know how much a three-sensor design under-counts before they publish an index.

## What you need
1. Sensor records per site with a timestamp and an on-battery flag (or any power-on/power-off report).
2. A count of events per site and period, made with the same rule as the paper (see README).
3. The sensor count per site, and if you can, the share of time the sensors reported (uptime).
4. A laptop or phone with a browser. The CSV tool (`python -m outage_gap`) needs only Python and works without internet after installation.

## A realistic workflow
1. **Count** events per site and month with the paper's rule.
2. **Check uptime.** If it is below 0.65 at many sites, do not trust the curve; fix the sensors first.
3. **Run the CSV tool** on all sites at once. Review the `warnings` column.
4. **Report quarters or years**, not single months, and report the 80% range next to the corrected count.
5. **Say what the number is**: a corrected count of outages that two or more sensors would have seen, not a utility record.

## Recalibrating for a new city
The curve was measured in Accra. A second city needs its own dense reference site (about 15 or more sensors under one transformer for several months):
1. Extract the events of the dense site with the paper's rule.
2. Run `reproduce/run_subsampling.py` on its device file (columns: `device, bin, n_obs, n_unpowered, site_id`). Save the bin counts as in `reproduce/extract_sites.py`.
3. Run `calibration/build_calibration.py` and replace `outage_gap/calibration.json`.
4. Compare the new detection shares with 0.37 (3 sensors), 0.47 (5) and 0.62 (8). If they differ by more than a few points, the Accra curve should not be used there.

## What it cannot do
- It cannot find outages that no sensor saw, or transformers with no sensor.
- It does not correct outage duration (SAIDI).
- It is not a substitute for a utility outage record where one exists. Use it where the sensors are the only low-voltage record.
- It did not transfer to Sierra Leone in a preliminary check (6 site-months), so it must be recalibrated outside Accra.

## Practical limits in low-resource settings
- Data bundles and power cuts: use the offline CSV tool, and keep the Streamlit app for demonstrations.
- Staff time: counting events from raw device files is the hard step, not the estimate. `python -m outage_gap.count_events` applies the counting rule to a CSV with `device, time, on_battery`; it was checked on the real nLine bin files of the two dense Accra sites (full-site count equal to the reference in all 86 site-months), but not on exports from other deployments, so check it on one site by hand first.
- Trust: always show the range and the warnings, never a single number. Every output says: not a utility record. Do not rank districts with a single month's estimate: at three sensors the typical single-month error is about 44%.
