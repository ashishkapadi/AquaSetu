# Verification of the hackathon build

## Real dataset and model

- Prepared the official Water-Futures/BWDF inflow workbook into 196,790 rows covering 10 measured districts.
- Verified source units, UTC-normalized unique hourly timestamps, nonnegative flows and missing-value counts.
- Preserved the original workbooks and recorded SHA-256 hashes and source URLs.
- Trained separate gradient-boosted tree regressors for the districts using shared chronological split boundaries.
- Selected the boosted-tree approach using validation MAE, then evaluated it on 29,081 held-out district-hours.
- Test MAE: 3.0951865686 m³; weekly baseline: 4.3201355524 m³; improvement: 28.3544%.
- Final forecasts refit on available history. Evaluation results remain separate from future predictions.

## Automated checks

`python -m pytest -q`: 18 tests passed.

Coverage includes temporal feature isolation, causal short-gap filling, rejecting fabricated timestamps and duplicates, complete model training/persistence, HTTP horizon conversion, CSV upload handling, negative/invalid supply rejection, zero/excess supply, demand caps, priority behavior and conservation across 200 randomized allocation scenarios.

Artificial data are used only by software tests in isolated temporary directories. They are not included in the production dashboard or its performance claims.

`npm.cmd run build`: passed. Vite reports a nonblocking bundle-size warning. Python dependencies report deprecation warnings; tests and real-data training complete successfully.

## Browser and API checks

- Real data load with correct source, m³ units, 10 districts, UTC dates and measured model scores.
- Latest-hour anomaly table and historical unusual-readings panel.
- Zero-supply scenario: 0% coverage and all demand unmet.
- Excess supply of 1,000 m³ for the next hour: full demand coverage and approximately 261.4 m³ unused.
- Priority scenario: 590 m³ total supply, hospital priority 5, others 1; hospital reaches full coverage while other districts share the remaining supply.
- Switching to 24 hours changes the forecast to 24 points and resets the suggested supply for that horizon.
- A 24-hour API scenario with 10,000 m³ supply allocates exactly that volume and reports the remaining deficit.
- Data/setup controls identify the prepared file, auto-fill its units and support retraining.

## Limits to communicate

The main accuracy score is next-hour, rolling-origin MAE. Separate multi-hour evidence covers five eligible weekly origins across ten districts; it is a limited sample. At 24 hours, hourly MAE is 3.538 m³ versus 4.367 m³ baseline. Total district volume MAE is 33.269 m³ versus 43.719 m³ baseline. Supply and priority weights are scenarios. Physical pipe constraints and weather predictors are outside this build. Inflow is a demand proxy; unusual readings are not confirmed leaks. Source dates describe historical replay, not live telemetry.

Additional checks cover evaluation persistence, measured-series evidence for simulated-zone imports, recursive origin isolation and total-volume error arithmetic, district-series API validation, dedicated analysis API, direct page refresh, and unknown API paths returning 404.

The separate-page interface was verified in the in-app browser: all seven pages render; the hospital's 24-hour series displays 24 forecast rows; supply 10,000 m³ and hospital priority 5 persist across Allocation → Zones → Allocation; allocations update to 577.1 m³ for the hospital and 10,590.3 m³ system shortage. Data mapping selects the real CSV's timestamp, consumption, zone and m³ unit. UI retraining completes and refreshes evidence. Refreshing `/analysis` directly works, and selecting DMA 10 changes the held-out chart. Forecast and evaluation chart legends are visible. No browser console errors were recorded during these checks.

Astra's code review found an upload timezone-labeling bug, fixed by carrying UTC normalization from CSV preparation through serialization. The training test now covers an offset-aware CSV without metadata and verifies UTC source and evaluation timestamps.
