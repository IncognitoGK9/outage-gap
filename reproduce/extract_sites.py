"""Pull the rows of sites 3 and 4 out of the raw nLine GridWatch Accra parquet files.
Usage: python3 -I extract_sites.py path/to/ghana/*.parquet  > no stdout; writes sites34.csv
Data: nLine GridWatch public dataset, CC BY-NC 4.0, https://nline.io/public-data/gridwatch
"""
import sys
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pcsv
import pyarrow.parquet as pq

COLS = ["device", "bin", "n_obs", "n_unpowered", "n_lowv", "v_mean", "site_id"]
tabs = []
for f in sorted(sys.argv[1:]):
    t = pq.read_table(f, columns=COLS)
    t = t.filter(pc.is_in(t["site_id"], value_set=pa.array([3, 4], type=t["site_id"].type)))
    if t.num_rows:
        tabs.append(t)
pcsv.write_csv(pa.concat_tables(tabs), "sites34.csv")
