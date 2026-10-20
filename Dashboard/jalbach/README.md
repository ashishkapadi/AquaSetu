# Smart Water Redistribution

A complete local Streamlit application for multi-zone demand forecasting, unusual-consumption detection, shortage planning and direct water redistribution. Python, pandas/NumPy, scikit-learn, Plotly, PyDeck, SciPy and joblib. The public regional view retrieves dated water reports automatically. The optional synthetic demo runs offline; actual demand forecasting requires an authorized utility/meter feed. No hydraulic model is required.

## Run

Python 3.9–3.12 is recommended. From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open http://localhost:8501. **Public regional reports** is the default view for Mumbai, Thane, Kalyan–Dombivli and nearby areas. It automatically retrieves public reservoir reports and prominently shows observation dates, provenance and stale-data warnings. These reports cannot support neighbourhood demand forecasts.

**Live connection** accepts an authorized utility/meter JSON API, refreshes every minute while open, persists the last validated snapshot and automatically trains on changed observations when enabled. CSV forecasting is also available under **Upload CSVs**. A verified public interval-consumption feed for these cities has not yet been found. See [live-data setup and source investigation](docs/LIVE_DATA.md).

**Synthetic demo** remains available explicitly for testing the full modelling pipeline. It is never substituted for real data on failure. Models are fingerprinted and reused until history/weather changes or retraining is requested.

To generate example files, train models and export reports without the UI:

```bash
python -m smart_water
python -m pytest -q
```

The included `data/examples/*.csv` files are synthetic examples for developers; use **Upload CSVs** to load them, or use an automatic API connection. `requirements-lock.txt` records the verified Python 3.9/macOS environment; `requirements.txt` provides portable compatible ranges.

## Dashboard

- **Overview:** future demand and supply, shortage before/after, at-risk zone count, historical anomaly-alert count, interactive coordinate map and balance charts.
- **Demand forecast:** zone history, recursive forecasts, empirical bands, baseline comparison, per-zone and overall MAE/RMSE and test coverage.
- **Anomaly alerts:** historical monitoring replay with actual, expected, origin, signed deviation, threshold, severity and an investigation explanation.
- **Redistribution:** direct transfers with reasons and the complete interval balance, including residual shortages and configurable risk categories.
- **Data & methodology:** downloadable inputs, data preview, saved model metadata and modelling assumptions.

Controls include supported horizons (up to 72 hours or 7 days, subject to evaluated history length), model choice, upper-band conservative planning, allocation method, supply percentage, weather scenario shifts and risk thresholds. Shortage categories are not probabilities. Provider supply must cover every requested future zone-interval; forecasts and historical evaluation remain accessible even when supply is incomplete.

## Interval data contracts

| File | Required columns | Optional columns |
|---|---|---|
| Consumption | `timestamp,zone_id,consumption_m3` | — |
| Supply | `timestamp,zone_id,available_supply_m3` | — |
| Zones | `zone_id,zone_name,priority_weight` | `latitude,longitude` together |
| Connections | `source_zone,destination_zone,capacity_m3` | `transfer_cost` (default 0) |
| Weather | `timestamp,temperature,rainfall` | — |

Volumes and connection capacities are **m³ per declared interval**. Costs are nonnegative relative cost per m³. Priorities must be positive. Temperature is °C; rainfall is mm per interval. Coordinates are decimal degrees. Use ISO 8601 timestamps with offsets; naive timestamps are interpreted as UTC. Calendar features use UTC. Zone identifiers are strings; providers should preserve leading zeros.

Choose actual hourly or daily resolution. No fabricated hourly observations or upsampling. All zones share a complete regular grid and common history start/end. Minimum history is 840 hourly intervals (35 days) or 70 daily observations. Missing readings, missing supply, duplicate keys, invalid timestamps, negative/nonfinite volumes and unknown zones produce readable errors. A measured zero is retained. Gaps must be reconciled externally; the app does not guess or silently impute them. Numeric CSVs cannot establish physical units; the provider is responsible for conversion.

For **cumulative meters**, the reusable `cumulative_to_intervals` helper accepts `timestamp,zone_id,meter_m3`; the live provider adapter must perform conversion before publishing its snapshot. Readings are interpreted at interval ends. Within-zone differences become interval volumes, and each zone's first reading is dropped because its previous reading is unknown. A decrease is a possible reset: the affected interval cannot be recovered reliably from these readings, so conversion stops with a timestamp/zone error. Reconcile resets from meter logs and provide corrected interval volumes. Never take an absolute difference or assume a reset happened exactly at the interval boundary.

Supply is a delivery schedule for each interval. Reservoir stock must first be converted into a feasible schedule, respecting the total storage budget; do not repeat that stock every hour. Connections are **directed**; reverse transfers require a separate row. An empty connections CSV with the required headers permits no transfers. Missing coordinates disable only the map. The PyDeck coordinate map has no remote basemap, so it needs no tile service or map credentials.

Weather is optional. When supplied it must cover all history. Provider future weather is excluded because the format has no forecast issue time. Forecasts instead use an explicitly labelled climatology scenario based only on weather available before each origin, plus user-selected future shifts. No future observations enter evaluation. Holidays are not inferred; a jurisdiction-specific, versioned calendar would be needed to add them.

## Model and evaluation design

`smart_water/forecast.py` implements a seasonal-naive baseline (matching interval last week) and a pooled Random Forest with one-hot zone identity, hour sine/cosine, weekday/weekend, month/season, lag 1, daily/weekly lags, and past rolling mean/standard deviation. Observed weather is available for training; future weather uses the scenario above. Trees do not require feature scaling. Every lag and rolling window ends before the target timestamp. Recursive prediction appends predictions, never actual future consumption.

The split is chronological **60% train / 20% validation / 20% test**, using three non-overlapping rolling origins within each evaluation segment. The model is frozen within each segment: training-only fit for validation; train-plus-validation fit for test. As origins advance, already-arrived observations can update lag inputs. Horizon is capped so the three evaluation blocks fit (up to 72 hourly or 7 daily steps). Metrics pool the sampled origins, not every historical timestamp. The last origin reaches the end of history.

Per-zone 90th-percentile absolute validation residuals produce symmetric bands (lower limit clipped at zero). Test coverage is reported independently. Per-zone 99th-percentile absolute validation residuals calibrate both high and low usage alerts; a small numerical floor prevents division/threshold degeneracy. Medium exceeds this threshold, High exceeds twice it. Anomalies remain in the data. These are possible unusual usage, leakage or sensor issues, **not confirmed leaks**.

Bands pool forecast leads and may miscalibrate during drift, weather scenario changes, or after final refitting. They are not simultaneous guarantees across zones/time. Conservative mode uses each interval's upper band as planned demand, not a calibrated joint reliability target. Final deployment training uses all history. Validation/test scores refer to the earlier fitted models; no future accuracy claim is made.

Artifacts contain model, calibration, evaluation records, alerts and metadata. A SHA-256 history/weather/resolution fingerprint prevents accidental reuse after data changes. JSON metadata records split boundaries, trained-through date and software versions. Artifacts are local joblib files generated by this app; **never load untrusted joblib/pickle files**. The app does not offer model uploads.

## Redistribution

For each interval, shortage is `max(0, planned_demand - supply)` and surplus is the reverse. Shortage percentage safely returns zero for zero demand.

The baseline sorts feasible direct edges by recipient allocation score, then cost and deterministic IDs, transferring the minimum of donor surplus, recipient need and edge capacity.

The allocation score is `priority_weight × (1 + shortage_pct / 100) × (1 + predicted_demand / max_zone_predicted_demand)` within each interval (the denominator is floored at 1e-9). Higher demand and greater shortage severity increase priority when other factors are equal. These bounded multipliers express a planning policy, not learned probabilities.

The LP maximizes allocation-score-weighted served shortage, equivalent to minimizing weighted unmet demand. A second LP minimizes transfer cost while enforcing the optimal weighted volume from the first. This is a true two-stage objective: a large transfer cost cannot override priority. Both methods enforce nonnegativity, connection capacity, donor retention and recipient needs. Total water is conserved per interval. Disconnected zones cannot exchange; there is no multi-hop transit. Insufficient water produces a feasible plan with residual shortage, not fictitious supply.

This is a **planning model**, not hydraulic validation. Pipe pressure, head loss, pump energy, transfer losses, travel time, storage carryover and within-interval timing are not simulated. WNTR is intentionally not a dependency; adding it requires a calibrated physical network and separate validation.

## Project layout

```text
app.py                      Streamlit dashboard and automatic source selection
smart_water/live.py         Live API validation, SQLite snapshots, issued forecasts
smart_water/regional.py     Dated public regional reservoir reports
smart_water/data.py         Validation, cumulative conversion, seeded demo
smart_water/forecast.py     Features, training, backtesting, alerts, artifacts
smart_water/allocation.py   Shortage calculations, greedy and LP allocation
smart_water/__main__.py     Offline reproducible demo and exports
data/examples/              Synthetic developer example CSVs
artifacts/                  Locally generated models and reports (gitignored)
tests/                      Data, forecasting, optimization and UI tests
docs/REFERENCES.md          Source inspection and licensing notes
```

The pasted specification ended at the start of its “Demand forecast” dashboard subsection. The implemented views cover all complete functional requirements preceding that truncation.

## CSV forecasting and weather impact

Choose **Upload CSVs** in the sidebar, or **Upload CSV & generate forecasts** on the unconnected live-data page. Upload consumption history and select **Generate forecasts**. Consumption alone enables forecasts and anomaly backtests. Future supply is optional for shortage calculations; explicit connections are required for transfers. Missing supply is not replaced with zero. Missing metadata uses zone IDs as labels and equal priority weights, with no invented coordinates.

For weather effects, include `temperature` (°C) and `rainfall` (mm/interval) in every historical consumption row, or provide the optional weather CSV. Weather must agree across zones at the same timestamp. Download `data/examples/consumption_with_weather.csv` for a complete **synthetic** single-file example.

In **Demand forecast**, choose **Random forest** or **Extra trees**, expand **Scenario & risk settings**, and adjust temperature/rainfall shifts. **How weather changes predicted demand** compares the same model/history/horizon under baseline weather and adjusted weather, reports the volume and percentage difference, plots both paths, and exports interval weather inputs plus their predicted demand difference. Baseline weather uses past hour-of-day averages; these are scenarios, not a fetched meteorological forecast. Effects are learned associations, not guaranteed causal responses. Seasonal naive has no weather features; weather controls are disabled for it. Without historical weather the app does not invent an effect.

The workspace includes **Demand forecast**, **Anomaly alerts**, **Shortage prediction**, and **Redistribution**. Shortage prediction shows zone totals and interval risk before transfers. Alerts highlight each affected zone’s most recent dated detection; an old event is not labelled as a current anomaly.

## Train the prepared CSV demo

Run `.venv/bin/python train_demo.py` to validate the four files in `outputs/demo_csv_bundle`, train/evaluate Random forest, Extra trees and a neural network against Seasonal naive, select by validation MAE, refit on all history, and save the models in `artifacts`. Results include `neural_network_epochs.csv`, held-out metrics, 72-hour forecasts and full/80%-supply redistribution scenarios in `outputs/demo_training_results`.

Select **Demo CSV bundle** in the website to load these exact inputs and reuse the saved model. The overview map shows latest observed interval demand, forecast-period demand and peak shortage severity. Demand forecast compares the selected horizon against the same intervals last week. These files are synthetic and end in September 2026; predictions start after their last observation, not after today's date.

## Area shortage map

Open **Shortage map** to compare before/after risk, choose a forecast interval or full horizon, and inspect demand, supply, proposed incoming transfers and remaining unmet need. Existing supply/weather controls recalculate the view. Colour represents worst interval severity; shortages sum positive interval deficits rather than netting against other times. Conservative mode uses upper-band planning demand.

Synthetic mode draws explicitly illustrative service areas around approximate Mumbai-region city locations. Real datasets use point markers until a GeoJSON FeatureCollection is uploaded under Area boundaries. Provide one WGS84 Polygon/MultiPolygon per zone with `properties.zone_id` matching the data. All zones must be covered, rings closed and coordinates finite. The application checks structure and matching IDs, not boundary provenance or topological correctness. CARTO/OpenStreetMap provides the online basemap and attribution; turn off Show street basemap if tiles are unavailable. Transfer arcs show declared connections, not hydraulic pipe routes.

## Interactive all-area dashboard

**Live dashboard** shows all zones together and recalculates on widget changes (sliders commit when released). Forecast & planning opens on this page. Per-zone demand cards, baseline-versus-scenario curves, supply/shortage deltas, remaining risk and transfer tables update using the selected inputs. The comparison baseline holds model, horizon, conservative setting and thresholds constant, using 100% original supply and zero weather shifts. Deltas are not comparisons against the previous click.

Synthetic/CSV inputs remain fixed snapshots. Calculation time is labelled separately from observation time. Connected API data uses the existing minute refresh while the app is open; stale feeds suppress operational planning. Forecast-only inputs still display all-area demand without manufacturing supply. Export buttons provide all-area summary and interval comparisons.

### Admin allocation simulator

In Live dashboard, select **Admin allocation**. Choose donor, connected recipient, period and percentage of donor supply to reassign. Each interval is capped at declared connection capacity and total supply is conserved. A manual choice may reduce donor demand coverage; the dashboard explicitly flags increased unmet demand, coverage percentages, first shortage time and area-level supply/shortage changes. The baseline includes current sidebar supply scaling and weather but precedes automatic redistribution. An automatic allocation alternative is shown separately, never layered on a manual move that already consumes capacity.

This is a planning simulator, not authenticated role-based administration or remote infrastructure control. Demo data represents fictional zones, not verified cities. Stale/missing supply prevents operational simulation. Coverage measures modelled demand served, not health or survival. Exports provide a proposed schedule and impact assessment; no provider records are modified.

Demo zone labels: N = Thane, C = Mumbai, E = Kalyan, S = Dombivli, W = Navi Mumbai. Internal IDs remain stable so the saved model and connection references remain compatible. City labels and approximate map markers do not turn synthetic readings or assumed transfers into real municipal data.
