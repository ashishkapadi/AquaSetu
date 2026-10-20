# Verification

Verified locally on 2026-10-11 with Python 3.9.6; resolved packages are in `requirements-lock.txt`.

- `python -m smart_water`: successful synthetic generation, model training/evaluation, joblib/JSON persistence, forecast and allocation CSV export.
- `python -m pytest -q`: 22 passing tests, including strict input contracts, cumulative resets, leakage boundaries, recursive feedback, model persistence, daily resolution, cost/priority ordering, disconnected/no-multi-hop networks, randomized allocation invariants and Streamlit navigation/controls.
- Local Streamlit health endpoint: `ok`.
- Browser inspected: overview metrics, Plotly charts and the self-contained PyDeck coordinate map. Preview saved as `dashboard-preview.png`.
- All five views and conservative/baseline controls exercised with Streamlit AppTest. File upload controls verified; the upload parsing/validation and daily data pipeline are covered at the Python layer. A full browser upload workflow was not separately exercised.

The default synthetic 24-hour point-forecast/optimization scenario produces approximately 1,861.0 m³ shortage before transfers and 142.3 m³ afterward. This is a generated demo result, not observed city performance. Random Forest test MAE is approximately 8.04 m³ per zone-interval versus 8.60 m³ for seasonal naive, on the sampled held-out test windows. Metrics can vary with dependency versions; run the CLI to reproduce them in your environment.

## Automatic-data update — 2026-10-11

- Removed CSV-upload workflow from the UI; default is the automatic public regional report view.
- Final regression: **35 tests passed**. Includes API contracts, timestamp safety, durable outage fallback, stale observations, prevention of hindsight alerts, observation-date extraction and a mocked-provider end-to-end UI test. The latter uses explicitly synthetic fixtures, not real utility data.
- Actual public adapter requests succeeded for Mumbai, Thane and Kalyan–Dombivli. Retrieved observation dates were respectively **2026-10-01**, **2026-08-11**, and **2026-08-11**; all were correctly marked stale. The fetch date was 2026-10-11. These are independent community republications, not independently verified municipal meter readings.
- Browser verified Mumbai and Kalyan–Dombivli selection, report dates and stale warnings. Screenshot: `regional-preview.png`.
- Utility integration has not been validated against a real municipal consumption endpoint because no suitable public endpoint was verified. Actual live demand forecasting and real redistribution remain dependent on that source and operational network/supply data.
- Local Python 3.9.6 uses LibreSSL and emits urllib3's compatibility warning. HTTPS requests succeeded during verification; use a modern Python build with supported OpenSSL for deployment. TLS verification was not disabled.

## CSV and weather comparison update — 2026-10-11

- Restored Upload CSVs alongside public reports, live connections and the synthetic demo, with a direct button on the unconnected live page.
- Consumption-only CSVs now enable forecasting without inventing supply. Optional metadata, delivery, connection and weather files enable the additional features.
- Supports temperature/rainfall in the consumption CSV or a separate weather CSV; contradictory same-timestamp weather is rejected.
- Regression suite: **38 tests passed**. UI tests also rerun after the final navigation changes.
- Browser verification used the explicitly synthetic `data/examples/consumption_with_weather.csv`: uploaded 10,800 rows, generated forecasts, selected Demand forecast and adjusted temperature by +0.5 °C. For example zone C over 24 hours, baseline 2,896.5 m³ changed to 2,907.9 m³ (+11.4 m³, +0.39%). This is a model scenario on synthetic data, not a real-city result or causal estimate.
- The weather-impact view exposes both demand curves, selected scenario shifts, interval weather inputs and a downloadable comparison. Screenshot: `weather-impact-preview.png`.
