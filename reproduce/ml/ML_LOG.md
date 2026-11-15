# ML experiments (15 Nov 2026), log of each step
- E33 (exp1/exp2): learned estimator on columns obs1/obs2 of draws_v3. INVALID: those columns count events of the FULL site's event list, so they leak the answer. Numbers (13-21% error) must not be used.
- E34 (mk_draws, exp3): clean draws rebuilt from raw bins, features from the subset's OWN readings only (events seen by exactly 1, 2, 3, 4+ sensors, uptime). Check: shares 0.41/0.32 at k=3 match shipped 0.374. Leave-one-site-out, median abs error k=3: raw 63/71, divide 45/45, ridge 17/39, gboost 16/20. Ranges from training-site residuals: coverage 37-78% (shift between sites).
- E35 (exp4): train on 700 simulated worlds only, test on real: k=3 error 25.3 (site 3), 28.8 (site 4) vs divide 45.4/45.0, raw 63/71.
- E36 (exp5): Sierra Leone, 6 site-months, reference 8 sensors: raw 9.8, Accra share 146.6, sim-trained 17.5 (bias +16). No gain.
- E37 (exp6): range from held-out simulated worlds: coverage only 22-34% on real Accra (real sites differ from simulated worlds). Point error stable over 3 seeds: k=3 27.5 / 29.3.
- E38 (exp7): sim-trained point estimate + range calibrated on one real site, tested on the other, 3 seeds: k=3 error 28.0/29.3 vs divide 45.4/45.0; coverage 83.4/75.8 vs 78.5/79.5; width 1.3/1.1 vs 3.6/1.6. At k=8 site 4: gboost 27.4 vs divide 23.0 (no gain).
