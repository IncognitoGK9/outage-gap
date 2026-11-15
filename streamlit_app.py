"""OutageGap: Streamlit screen. Run: streamlit run streamlit_app.py"""
import io
import json
import pandas as pd
import streamlit as st
from outage_gap import demo
from outage_gap.batch import run as run_batch
from outage_gap.calibrate import calibrate
from outage_gap.core import CAL, check_calibration, estimate, plan, sizes_of
from outage_gap.count_events import count_by_site

st.set_page_config(page_title="OutageGap", page_icon="⚡", layout="centered")
st.title("OutageGap")
st.subheader("How many outages did our sparse sensor site miss?")
st.write("Plug-in sensor sites with a few sensors count only some outages. Enter what your site counted "
         "(events seen by at least 2 sensors) and get an estimate of the full count and an 80% range. "
         "The shipped curve was measured on two dense sites in Accra, Ghana. **For another place, measure your own curve "
         "from your own dense sites** (tab 2). Research prototype.")

# ---- which curve is in use (sidebar, so every tab uses it) -------------------------------------------------
if "curves" not in st.session_state:
    st.session_state["curves"] = {}
curves = {"Shipped curve (Accra)": None, **st.session_state["curves"]}
choice = st.sidebar.radio("Curve in use", list(curves), help="Your own curves appear here after you measure or load them.")
cal = curves[choice]
sizes = sizes_of(cal)
st.sidebar.caption(f"Sensor counts in this curve: {sizes[0]} to {sizes[-1]}.")
st.sidebar.caption("Source: github.com/incognitogk9/outage-gap")

tabs = st.tabs(["1 Estimate", "2 Your own curve", "3 Raw sensor files", "4 Dummy sites", "5 Plan sensors", "6 Many sites (CSV)"])

# ---- 1 Estimate --------------------------------------------------------------------------------------------
with tabs[0]:
    c1, c2 = st.columns(2)
    sensors = c1.number_input("Sensors at the site", min_value=sizes[0], max_value=sizes[-1], value=min(max(3, sizes[0]), sizes[-1]), step=1)
    events = c2.number_input("Outage events counted in the period", min_value=0, value=24, step=1)
    use_uptime = st.checkbox("I know the sensors' uptime")
    uptime = st.slider("Sensor uptime (share of time reporting)", 0.0, 1.0, 0.8, 0.05) if use_uptime else None
    r = estimate(int(sensors), int(events), uptime, cal)
    m1, m2, m3 = st.columns(3)
    m1.metric("Estimated total", f"{r.estimated_total:g}")
    m2.metric("Counted", r.observed_events)
    m3.metric("Estimated missed", f"{r.estimated_missed:g}")
    st.write(f"80% range for the total: **{r.range_80[0]:g} to {r.range_80[1]:g}**. "
             f"Detection share used: {r.detection_share:.2f} (the site counts about this share of the outages that 2 or more sensors saw).")
    chart = pd.DataFrame({"Bar": ["1 Counted", "2 Low", "3 Estimate", "4 High"],
                          "Outages": [r.observed_events, r.range_80[0], r.estimated_total, r.range_80[1]]})
    st.bar_chart(chart, x="Bar", y="Outages", x_label="", height=230)
    for w in r.warnings:
        st.warning(w)

# ---- 2 Your own curve --------------------------------------------------------------------------------------
with tabs[1]:
    st.write("Upload the raw sensor file of your **dense** sites (many sensors per site, for example 8 or more). "
             "The tool draws random small groups of sensors, counts events from each group alone, and compares with the "
             "full site. The result is a curve for your place. Columns: `device, bin, n_obs, n_unpowered` or "
             "`device, time, on_battery`; an optional `site` column names the site.")
    if "flash" in st.session_state:
        st.success(st.session_state.pop("flash"))
    up = st.file_uploader("Dense sites file (CSV)", type="csv", key="dense")
    use_dummy = st.checkbox("Use the two dummy dense sites instead (synthetic, for trying it out)")
    with st.expander("Settings"):
        pick = st.multiselect("Sensor counts to measure", [2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16], default=[3, 4, 5, 6, 7, 8])
        draws = st.slider("Random groups per site-month and size", 5, 100, 20)
        min_sensors = st.number_input("A dense site-month needs at least this many sensors", 3, 40, 8)
        min_cov = st.slider("...each reporting in at least this share of 30-minute bins", 0.3, 1.0, 0.6, 0.05)
    name = st.text_input("Name for this curve", "My dense sites")
    if st.button("Measure my curve", disabled=up is None and not use_dummy):
        try:
            with st.spinner("Drawing random groups of sensors... large files can take a few minutes."):
                data = demo.build()["dense"] if use_dummy else pd.read_csv(up)
                new = calibrate(data, pick, draws, 1, int(min_sensors), min_cov)
            st.session_state["curves"][name] = new
            st.session_state["flash"] = f"Done. '{name}' is now in the sidebar under 'Curve in use'."
            st.rerun()                                   # redraw so the sidebar list shows the new curve
        except ValueError as e:
            st.error(str(e))
    for nm, cv in st.session_state["curves"].items():
        st.markdown(f"**{nm}**: {cv['n_sites']} site(s), {cv['n_site_months']} site-months, range from {cv['range_method']}.")
        st.dataframe(pd.DataFrame([{"Sensors": int(k), "Detection share": p["c"], "Range low (10%)": f"{p['err_q10']:+.0%}",
                                    "Range high (90%)": f"{p['err_q90']:+.0%}", "Median single-month error": f"{p['median_abs_err']:.0%}"}
                                   for k, p in cv["k"].items()]), hide_index=True)
        for w in cv["warnings"]:
            st.caption("Note: " + w)
        st.download_button(f"Download '{nm}' (JSON)", json.dumps(cv, indent=2), f"{nm.replace(' ', '_')}.json", "application/json", key="dl" + nm)
    saved = st.file_uploader("Or load a curve you saved earlier (JSON)", type="json")
    if saved is not None and st.button("Load this curve"):
        try:
            st.session_state["curves"][saved.name] = check_calibration(json.loads(saved.getvalue()))
            st.session_state["flash"] = f"Loaded. '{saved.name}' is now in the sidebar."
            st.rerun()
        except (ValueError, json.JSONDecodeError) as e:
            st.error(f"Not a usable curve file: {e}")

# ---- 3 Raw sensor files ------------------------------------------------------------------------------------
with tabs[2]:
    st.write("Upload the raw sensor file of your **sparse** sites. The tool counts events by the rule (seen by at least 2 sensors) "
             "for each site and period, then estimates the total with the curve in use. Optional `site` column.")
    period = st.selectbox("Period", ["quarter", "month", "year", "all"], index=0)
    up2 = st.file_uploader("Sparse sites file (CSV)", type="csv", key="sparse")
    use_dummy2 = st.checkbox("Use the dummy sparse sites instead")
    if up2 is not None or use_dummy2:
        try:
            rows = count_by_site(demo.build()["sparse"] if use_dummy2 else pd.read_csv(up2), period)
            out = []
            for x in rows:
                try:
                    e = estimate(x["sensors"], x["events_2plus"], x["uptime_estimate"], cal)
                    out.append(dict(site=x["site"], period=x["period"], sensors=x["sensors"], counted=x["events_2plus"],
                                    estimated_total=e.estimated_total, estimated_missed=e.estimated_missed,
                                    low_80=e.range_80[0], high_80=e.range_80[1], uptime=x["uptime_estimate"]))
                except ValueError as err:
                    out.append(dict(site=x["site"], period=x["period"], sensors=x["sensors"], counted=x["events_2plus"], error=str(err)))
            table = pd.DataFrame(out)
            st.dataframe(table, hide_index=True)
            st.download_button("Download estimates (CSV)", table.to_csv(index=False), "outage_gap_analysis.csv", "text/csv")
            st.caption(f"Curve used: {choice}. Short periods are noisy; prefer quarters or years.")
        except ValueError as err:
            st.error(str(err))

# ---- 4 Dummy sites -----------------------------------------------------------------------------------------
with tabs[3]:
    st.write("Dummy sites are invented data with a known true count, so you can see the tool work and see where it fails. "
             "Two dense sites (16 sensors) teach a curve; four sparse sites are then estimated and compared with the truth.")
    st.dataframe(pd.DataFrame(demo.catalog()), hide_index=True)
    if st.button("Run the dummy-site test"):
        res = demo.run()
        df = pd.DataFrame(res["rows"])
        st.write("**Mean absolute error by site (percent)**: raw count, shipped Accra curve, own curve measured on the dummy dense sites.")
        st.dataframe(pd.DataFrame(res["summary"]).rename(columns={
            "mean_abs_error_pct_raw_count": "Raw count", "mean_abs_error_pct_accra_curve": "Accra curve",
            "mean_abs_error_pct_own_curve": "Own curve"}), hide_index=True)
        st.write("**Quarter by quarter** (estimates and errors in percent against the true count)")
        st.dataframe(df[["site", "quarter", "sensors", "counted", "true", "accra_estimate", "own_estimate", "accra_error_pct", "own_error_pct"]]
                     .rename(columns={"accra_estimate": "Accra est.", "own_estimate": "Own est.", "accra_error_pct": "Accra err %",
                                      "own_error_pct": "Own err %"}), hide_index=True)
        st.info("The own curve is close in its own world (first, third and fourth sites). The Accra curve over-corrects there, "
                "because the dummy world detects more outages. The site with mostly small outages breaks the own curve and no "
                "warning appears: only dense sites near that site could show it. "
                "(The Accra curve looks good on that site by chance.)")
    st.download_button("Download dummy dense sites (CSV)", demo.all_dense_file(), "dummy_dense.csv", "text/csv")
    st.download_button("Download dummy sparse sites (CSV)", demo.all_sparse_file(), "dummy_sparse.csv", "text/csv")

# ---- 5 Plan sensors ----------------------------------------------------------------------------------------
with tabs[4]:
    target = st.slider("Share of the reference outages a site should count", 0.3, 0.95, 0.7, 0.05)
    p = plan(target, cal)
    if p["sensors_needed"]:
        st.metric("Sensors needed", p["sensors_needed"])
    else:
        st.warning("No tested sensor count reaches this share.")
    st.dataframe(pd.DataFrame(p["table"]).rename(columns={"detection_share": "share counted", "missed_per_100": "missed per 100",
                                                          "median_single_month_error": "median single-month error", "has_range": "has range"}),
                 hide_index=True)
    st.caption(p["note"])

# ---- 6 Many sites ------------------------------------------------------------------------------------------
with tabs[5]:
    st.write("Upload a CSV with columns `site, sensors, observed_events` and optionally `uptime`. "
             "Download the estimates. Sites outside the curve's sensor range are reported as errors, not guessed.")
    up3 = st.file_uploader("CSV file", type="csv", key="many")
    if up3 is not None:
        t = pd.read_csv(io.StringIO(run_batch(up3.getvalue().decode("utf-8"), cal)))
        st.dataframe(t, use_container_width=True)
        st.download_button("Download estimates (CSV)", t.to_csv(index=False), "outage_gap_estimates.csv", "text/csv")

with st.expander("How it works"):
    st.write("Estimated total = counted events ÷ detection share. The shipped detection share was measured by drawing random "
             "subsets of 3 to 8 sensors from two dense Accra sites (15 to 23 sensors, 86 site-months) and "
             "comparing them with the full site. Events are counted with at least 2 of the subset's own sensors. The range is the "
             "10th to 90th percentile of the error when the share from one dense site is applied to the other. "
             "Your own curve is measured the same way from your own dense sites.")
    st.table(pd.DataFrame([{"Sensors": k, "Detection share": CAL["k"][str(k)]["c"],
                            "Median single-month error (cross-site)": f"{CAL['k'][str(k)]['median_abs_err']:.0%}"} for k in sizes_of()]))
st.caption("Counts must follow the event rule in the paper (30-minute bins, sensor down if at least half its readings "
           "are on battery, events seen by 2 or more sensors). Not a utility record.")
