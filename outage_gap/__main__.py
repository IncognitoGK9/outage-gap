"""Command line: python -m outage_gap sites.csv > estimates.csv"""
import sys
from .batch import run

if len(sys.argv) != 2:
    sys.exit("usage: python -m outage_gap sites.csv   (columns: site,sensors,observed_events[,uptime])")
sys.stdout.write(run(open(sys.argv[1], encoding="utf-8").read()))
