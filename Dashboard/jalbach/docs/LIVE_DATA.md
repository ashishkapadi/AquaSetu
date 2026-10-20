# Automatic regional and utility data

## What is connected now

The default **Public regional reports** view automatically fetches published reservoir reports for Mumbai, Thane, Kalyan–Dombivli, Bhiwandi, Ulhasnagar, Ambarnath and Badlapur. It requires no CSV uploads or credentials. The source is the independent community site [MumbaiWaterLevel.com](https://mumbaiwaterlevel.com/), which attributes its readings to BMC / Maharashtra WRD. These values have not been independently reconciled against the official bulletins. The source is explicitly attributed in the UI.

The connector extracts the **Report as of / Data as of date**, not the current date in a page title. It fails closed on missing dates, missing values or invalid ranges. Readings older than two days are labelled OLD OBSERVATION. Fetch time is distinct from measurement date. A reachable website is not proof of fresh measurements. Public responses are cached for 15 minutes and checked while the browser session is active; manual refresh is available.

This is reservoir reporting, **not live metered consumption**. Reservoir stock does not establish municipal deliveries, ward demand, transfer capacity or hydraulic feasibility. No stock-to-demand conversion or exact water-demand claim is made. Shared reservoir totals must not be added across cities. Mumbai's Bhatsa accounting can differ from whole-dam accounting elsewhere.

## Regional investigation, 2026-10-11

- [BMC Hydraulic Engineer department](https://crmapp.mcgm.gov.in/irj/portal/anonymous/qlhydrlc): official department information. The main portal request returned a script/clickjacking shell rather than an accessible machine-readable water series.
- [BMC Disaster Management](https://dm.mcgm.gov.in/): reachable public application; examined public frontend data references. No ward consumption/supply history was verified.
- [KDMC pumping stations schema](https://maps.kdmc.gov.in/agserver/rest/services/KDMC_BASEMAP_24_04_2025/MapServer/104): indexed schema lists station attributes, including `consum_day`, but does not establish dated interval observations or units for that field. A read-only query returned an HTML configuration page, not JSON records. Never use one static `consum_day` value as an invented time series.
- [Thane public water-quality portal](https://wqms.thanecity.gov.in/static/index.aspx): water-quality reporting, not a verified consumption time series. Water-tax pages contain billing information, not public operational meter feeds; no private accounts were accessed.
- [Maharashtra regulator's Pravah description](https://mwrra.maharashtra.gov.in/wp-content/uploads/2025/02/GSG-Report-Oct-2024_compressed.pdf): reservoir reporting includes level/storage/rainfall/discharge; it does not establish a public neighbourhood-consumption feed.
- Public community reports for [Thane](https://mumbaiwaterlevel.com/thane-water-levels) and [Kalyan–Dombivli](https://mumbaiwaterlevel.com/kalyan-dombivli-water-levels) exposed old observation dates despite current-looking page headings. The UI flags this rather than presenting those readings as real-time data.

A verified live demand API for these municipalities has **not been found**. This is a finding from the inspected sources, not a claim that no such feed exists. Real demand forecasts remain blocked by access to actual interval consumption; redistribution additionally needs delivery schedules and connection capacities.

## Utility / meter gateway connection

The **Live connection** view is implemented for an authorized provider adapter, independent of the public reservoir view. A separate **Upload CSVs** mode is also available for offline forecasting. Configure the endpoint once in the sidebar or on the server:

```bash
export WATER_API_URL='https://your-provider.example/water/snapshot'
# If required, set WATER_API_TOKEN privately in the server environment.
.venv/bin/python -m streamlit run app.py
```

This is an integration contract, not a claim that a particular municipality already exposes this endpoint. A city/provider-specific adapter must convert that provider's documented API/database/IoT format into the contract below. An arbitrary website URL will not work.

The token is sent as a Bearer header only when the endpoint matches the configured WATER_API_URL. It is never included in UI output, SQLite snapshots or source control. API URLs must use HTTPS (HTTP allowed only for localhost gateways), without URL-embedded credentials. Redirects are not followed. Read timeouts and a 25 MB snapshot limit prevent unbounded responses.

### Snapshot contract

GET returns a full, bounded rolling snapshot with this shape (illustrative schema only, not real readings):

```json
{
  "source_name": "Utility name and dataset identifier",
  "units": "m3",
  "timestamp_semantics": "interval_end",
  "frequency": "h",
  "history": [{"timestamp": "2026-10-11T05:00:00Z", "zone_id": "ward-1", "consumption_m3": 100}],
  "supply": [{"timestamp": "2026-10-11T06:00:00Z", "zone_id": "ward-1", "available_supply_m3": 110}],
  "zones": [{"zone_id": "ward-1", "zone_name": "Declared zone", "priority_weight": 1}],
  "connections": [],
  "weather": []
}
```

The sample shows one row only; actual training needs at least 840 complete hourly intervals per zone or 70 daily intervals (`frequency: "D"`). History must include only completed intervals. Every timestamp must carry a timezone. Use the same grid for supply. The delivery schedule must cover the selected forecast horizon. Connection rows use `source_zone,destination_zone,capacity_m3,transfer_cost`; weather rows use `timestamp,temperature,rainfall`. Optional zone coordinates are supported. Cumulative meters must be reconciled and converted by the provider adapter, including resets. Incremental history events are not accepted yet: send complete rolling history. `history` and `zones` are required; `supply`, `connections` and `weather` may be omitted or empty. Missing optional inputs disable only the dependent features, and malformed supplied records still fail validation.

### Lifecycle and monitoring

- Polls automatically every minute while the browser session is active. This is not an unattended background service when every browser is closed.
- Validates provider records before replacing the last-good snapshot in local SQLite (`artifacts/live.sqlite3`). Does not replace missing readings with zeros or generated demo values.
- On an outage, the previous snapshot is clearly marked stale. Stale operational recommendations are paused. No prior snapshot means an explicit unavailable state.
- A successful response with observations more than two intervals old is still stale.
- The labelled automatic-training control defaults on for live data. A new history/weather fingerprint trains and evaluates a new model once, then persists it. Unchanged data reuses the saved artifact. Supply changes recalculate allocation without retraining.
- Saves forecasts with real issue timestamps and their original calibrated thresholds. Live alerts compare only saved predictions issued before the target interval ended against later-arriving observations. Historical model backtests are not substituted for live alerts. Scenario-weather experiments do not change monitored predictions.
- Forecasts remain estimates. Finite historical data, changing demand and unavailable future conditions prevent guarantees of exact future usage.

For always-on ingestion at larger scale, deploy a provider adapter and scheduler with explicit retention, authentication and operational monitoring. The current implementation is a local single-user dashboard with durable snapshots, not a multi-tenant production ingestion service.

### Feature parity with the demo

Live connection uses the same demand models, evaluation, weather scenario comparisons, conservative planning, supply scenarios, priority/optimized allocation, maps and CSV exports. The live feature availability panel explains missing inputs and selected-horizon supply coverage. Alerts use predictions actually issued before incoming observations, rather than demo backtests. Weather effects require historical temperature/rainfall and either trained tree model (Random forest or Extra trees); they are scenario estimates, not an external meteorological forecast. Public reservoir reports remain separate because they lack consumption history.
