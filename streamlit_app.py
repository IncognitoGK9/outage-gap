"""OutageGap: Streamlit screen. Run: streamlit run streamlit_app.py"""
import io
import pandas as pd
import streamlit as st
from outage_gap.batch import run
from outage_gap.core import CAL, SIZES, estimate

st.set_page_config(page_title="OutageGap", page_icon="⚡", layout="centered")
st.title("OutageGap")
st.subheader("How many outages did our sparse sensor site miss?")
st.write("Plug-in sensor sites with 3 to 8 sensors count only some outages. Enter what your site counted "
         "(events seen by at least 2 sensors) and get an estimate of the full count and an 80% range. "
         "Research prototype, calibrated on two dense sites in Accra, Ghana.")

c1, c2 = st.columns(2)
sensors = c1.number_input("Sensors at the site", min_value=SIZES[0], max_value=SIZES[-1], value=3, step=1)
events = c2.number_input("Outage events counted in the period", min_value=0, value=24, step=1)
use_uptime = st.checkbox("I know the sensors' uptime")
uptime = st.slider("Sensor uptime (share of time reporting)", 0.0, 1.0, 0.8, 0.05) if use_uptime else None

r = estimate(int(sensors), int(events), uptime)
m1, m2, m3 = st.columns(3)
m1.metric("Estimated total", f"{r.estimated_total:g}")
m2.metric("Counted", r.observed_events)
m3.metric("Estimated missed", f"{r.estimated_missed:g}")
st.write(f"80% range for the total: **{r.range_80[0]:g} to {r.range_80[1]:g}**. "
         f"Detection share used: {r.detection_share:.2f} (the site sees about this share of outages that 2 or more sensors saw).")

chart = pd.DataFrame({"Bar": ["1 Counted", "2 Low", "3 Estimate", "4 High"],
                      "Outages": [r.observed_events, r.range_80[0], r.estimated_total, r.range_80[1]]})
st.bar_chart(chart, x="Bar", y="Outages", x_label="", height=230)
for w in r.warnings:
    st.warning(w)
with st.expander("Many sites at once (CSV)"):
    st.write("Upload a CSV with columns `site, sensors, observed_events` and optionally `uptime`. "
             "Download the estimates. Sites outside 3 to 8 sensors are reported as errors, not guessed.")
    up = st.file_uploader("CSV file", type="csv")
    if up is not None:
        table = pd.read_csv(io.StringIO(run(up.getvalue().decode("utf-8"))))
        st.dataframe(table, use_container_width=True)
        st.download_button("Download estimates (CSV)", table.to_csv(index=False), "outage_gap_estimates.csv", "text/csv")
with st.expander("How it works"):
    st.write("Estimated total = counted events ÷ detection share. The detection share was measured by drawing random "
             "subsets of 3 to 8 sensors from two dense Accra sites (15 to 23 sensors, 86 site-months) and "
             "comparing them with the full site. Events are counted with at least 2 of the subset's own sensors. The range is the 10th to 90th percentile of the error when the share from one dense site is applied to the other.")
    st.table(pd.DataFrame([{"Sensors": k, "Detection share": CAL["k"][str(k)]["c"],
                            "Median single-month error (cross-site)": f"{CAL['k'][str(k)]['median_abs_err']:.0%}"} for k in SIZES]))
st.caption("Counts must follow the event rule in the paper (30-minute bins, sensor down if at least half its readings "
           "are on battery, events seen by 2 or more sensors). Not a utility record. Source: github.com/incognitogk9/outage-gap")
