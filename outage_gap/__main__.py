"""Command line for OutageGap.

  python -m outage_gap estimate sites.csv [--curve my_curve.json]      columns: site,sensors,observed_events[,uptime]
  python -m outage_gap count raw.csv [--period quarter]                events per site from a raw sensor file
  python -m outage_gap analyze raw.csv [--period quarter] [--curve my_curve.json]   count, then estimate
  python -m outage_gap calibrate dense.csv -o my_curve.json            measure your own curve from dense sites
  python -m outage_gap plan --target 0.7 [--curve my_curve.json]       sensors needed for a target share
  python -m outage_gap demo [--out folder]                             run on dummy sites (writes their CSV files)
  python -m outage_gap sites.csv                                       short form of 'estimate'
"""
import argparse
import json
import pathlib
import sys

import pandas as pd

COMMANDS = {"estimate", "count", "analyze", "calibrate", "plan", "demo"}


def load_curve(path):
    if not path:
        return None
    from .core import check_calibration
    try:
        return check_calibration(json.loads(pathlib.Path(path).read_text()))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"Cannot read curve file {path}: {e}")


def table(rows):
    print(pd.DataFrame(rows).to_string(index=False))


def main(argv):
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["estimate"] + argv                       # old short form
    p = argparse.ArgumentParser(prog="python -m outage_gap", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate"); e.add_argument("file"); e.add_argument("--curve")
    c = sub.add_parser("count"); c.add_argument("file"); c.add_argument("--period", default="all")
    a = sub.add_parser("analyze"); a.add_argument("file"); a.add_argument("--period", default="quarter"); a.add_argument("--curve")
    k = sub.add_parser("calibrate"); k.add_argument("file"); k.add_argument("-o", "--out", default="my_curve.json")
    k.add_argument("--sizes", default="3,4,5,6,7,8"); k.add_argument("--draws", type=int, default=40)
    k.add_argument("--seed", type=int, default=1); k.add_argument("--min-sensors", type=int, default=8)
    k.add_argument("--min-coverage", type=float, default=0.6)
    pl = sub.add_parser("plan"); pl.add_argument("--target", type=float, default=0.7); pl.add_argument("--curve")
    d = sub.add_parser("demo"); d.add_argument("--out", default=None)
    args = p.parse_args(argv)

    from .core import estimate, plan
    try:
        if args.cmd == "estimate":
            from .batch import run
            sys.stdout.write(run(open(args.file, encoding="utf-8").read(), load_curve(args.curve)))
        elif args.cmd == "count":
            from .count_events import count_by_site
            table(count_by_site(pd.read_csv(args.file), args.period))
        elif args.cmd == "analyze":
            from .count_events import count_by_site
            cal, rows = load_curve(args.curve), []
            for r in count_by_site(pd.read_csv(args.file), args.period):
                try:
                    x = estimate(r["sensors"], r["events_2plus"], r["uptime_estimate"], cal)
                    rows.append(dict(site=r["site"], period=r["period"], sensors=r["sensors"], counted=r["events_2plus"],
                                     estimated_total=x.estimated_total, estimated_missed=x.estimated_missed,
                                     low_80=x.range_80[0], high_80=x.range_80[1], uptime=r["uptime_estimate"]))
                except ValueError as err:
                    rows.append(dict(site=r["site"], period=r["period"], sensors=r["sensors"], counted=r["events_2plus"], error=str(err)))
            table(rows)
        elif args.cmd == "calibrate":
            from .calibrate import calibrate
            cal = calibrate(pd.read_csv(args.file), [int(x) for x in args.sizes.split(",")], args.draws, args.seed,
                            args.min_sensors, args.min_coverage)
            pathlib.Path(args.out).write_text(json.dumps(cal, indent=2))
            print(f"Wrote {args.out}: {cal['n_sites']} site(s), {cal['n_site_months']} site-months. Detection share by sensor count:")
            table([dict(sensors=int(s), share=v["c"], low_10pct=v["err_q10"], high_90pct=v["err_q90"]) for s, v in cal["k"].items()])
            for w in cal["warnings"]:
                print("Note:", w)
            print(f"Use it:  python -m outage_gap estimate sites.csv --curve {args.out}")
        elif args.cmd == "plan":
            r = plan(args.target, load_curve(args.curve))
            print(f"Sensors needed for a share of {args.target:g}: {r['sensors_needed'] or 'not reached in the tested range'}")
            table(r["table"]); print(r["note"])
        elif args.cmd == "demo":
            from . import demo
            res = demo.run()
            if args.out:
                out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
                (out / "dense.csv").write_text(demo.all_dense_file()); (out / "sparse.csv").write_text(demo.all_sparse_file())
                (out / "dummy_curve.json").write_text(json.dumps(res["own_curve"], indent=2))
                print(f"Wrote dense.csv, sparse.csv and dummy_curve.json to {out}/")
            print("Dummy sites (synthetic, truth known):"); table(demo.catalog())
            print("\nQuarter by quarter, error against the known truth (percent):")
            table([{k: r[k] for k in ("site", "quarter", "sensors", "counted", "true", "accra_estimate", "own_estimate",
                                      "accra_error_pct", "own_error_pct")} for r in res["rows"]])
            print("\nMean absolute error by site (percent):"); table(res["summary"]); print(res["note"])
    except (ValueError, OSError) as err:
        sys.exit(f"Error: {err}")


main(sys.argv[1:])
