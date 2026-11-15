"""Check that the function that builds YOUR curve gives exactly the shipped Accra curve on the real nLine rows.
Usage (from the repository root): python3 reproduce/check_own_curve_function.py sites34.csv
Takes about a minute. Same seed (1), 40 draws, sizes 3 to 8, 12 and 16 as reproduce/run_subsampling.py."""
import json
import pathlib
import sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from outage_gap.calibrate import curve_from_draws, draw_table

df = pd.read_csv(sys.argv[1], usecols=["device", "bin", "n_obs", "n_unpowered", "site_id"])
R, _ = draw_table(df, sizes=(3, 4, 5, 6, 7, 8, 12, 16), draws=40, seed=1)
shipped = pd.read_csv(ROOT / "calibration" / "calibration_draws.csv")
R["site"] = R.site.astype(int)
cols = ["site", "month", "k", "full", "obs2", "obs1", "obs_rb"]
print("draw table identical to the shipped draws:", R[cols].reset_index(drop=True).equals(shipped[cols].reset_index(drop=True)))
cal = json.load(open(ROOT / "outage_gap" / "calibration.json"))
print("curve identical to the shipped curve:", curve_from_draws(R, cal["source"], estimate_sizes=range(3, 9)) == cal)
