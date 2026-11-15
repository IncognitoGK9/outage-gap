"""Builds calibration.json from the subsampling draws.
c      = events a k-sensor site counts from its OWN readings (2+ of its sensors, events rebuilt from the subset readings, column obs_rb)
         / events seen by 2+ sensors of the full dense site. This is what a real sparse site does, so the shipped counting script matches it.
range  = 10th and 90th percentile of the CROSS-SITE relative error: the factor learned at one dense site is applied
         to the other dense site, so the range includes the difference between sites, not only sampling noise.
Sizes 3 to 8 go into 'k' (the sizes the estimator accepts); sizes 12 and 16 are kept in 'saturation' only.
The same code builds your own curve from your own dense sites: python -m outage_gap calibrate dense.csv
Run (from the repository root): python3 calibration/build_calibration.py calibration/calibration_draws.csv outage_gap/calibration.json"""
import json
import pathlib
import sys
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from outage_gap.calibrate import curve_from_draws

SOURCE = ("Accra dense sites 3 and 4, 86 site-months, Jan 2021 - Jul 2024; counting rule: events seen by 2+ sensors, "
          "rebuilt from the sensors the site has")
out = curve_from_draws(pd.read_csv(sys.argv[1]), SOURCE, estimate_sizes=range(3, 9))
json.dump(out, open(sys.argv[2], "w"), indent=2)
print(json.dumps(out, indent=2))
