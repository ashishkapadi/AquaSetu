# Requiem — dashboard API contract

Local hackathon application. React/Vite frontend in `frontend/`, FastAPI in `backend/`. API prefix `/api`; Vite proxies to http://127.0.0.1:8000. No hosted deployment.

## GET /api/status
`{ready: false, training: false, message: string, files: [{name: string, columns: string[], rows_preview: number}], error: string|null}`. When trained, ready=true. UI must show an honest onboarding state, never substitute fabricated metrics. Training may be in progress while a previous model is ready.

## POST /api/upload
Multipart field `file`, accepts CSV only. Returns `{name,columns,preview:object[]}`. Subsequent status lists it. Display upload errors.

## POST /api/train
JSON `{filename: string, timestamp_column: string, target_column: string, zone_column: string|null, unit: string}`. Unit is operator-declared, default `dataset units`; do not invent cubic metres. Starts background training, returns `{message}`. Poll status every 2 seconds only while training. Column choices from status or upload. Minimum 28 days of hourly history per series; missing actual targets excluded from evaluation. Use only genuine timestamp fields, not fabricated dates for arbitrary IDs.

## GET /api/dashboard?horizon=1|6|12|24
Returns:
```
{
  source: {name, url, unit, frequency, start, end, rows, observed_zones, simulated_zones, notes: string[]},
  forecast_origin: string,
  horizon: number,
  metrics: {model, model_mae, baseline_mae, selected_mae, improvement_pct, validation_model_mae, validation_baseline_mae, training_rows, validation_rows, test_rows, test_start, test_end, evaluation: string},
  history: [{timestamp, actual}],
  forecast: [{timestamp, predicted}],
  zones: [{id, name, share, predicted_demand, current_consumption, expected_current, anomaly: boolean, anomaly_direction: string, anomaly_threshold, priority: number}],
  default_supply: number,
  explanation: string[]
}
```
`history` last 72 actual hourly readings aggregated over real zones; `forecast` next selected horizon points. Forecast origin is last observed data timestamp (historical replay, not live city feed). Demand is summed volume over selected hours; current consumption is most recent hour. `model_mae` and `baseline_mae` evaluate next-hour predictions on identical unseen observations; `selected_mae` matches chosen model. Longer-horizon scores not claimed.

## POST /api/allocate
JSON `{horizon: 1|6|12|24, supply: number, priorities: {[zone_id]: number}, demand_multipliers: {[zone_id]: number}}`. Supply finite nonnegative; priorities 1–5; multipliers 0.5–2 represent explicit hypothetical surges, never measured events.
Returns `{supply, total_demand, allocated, shortage, unused_supply, coverage_pct, zones: [{id,name,demand,allocation,shortage,coverage_pct,priority,risk,explanation}]}`. risk `high|medium|low`. Debounce slider; display supply and priority input controls, allocation bars/table, and explanation. Handle zero supply, excess supply, fetch errors. Prefer no surge controls unless everything else finished.

## UI scope
Polished water-operations dashboard, light warm-neutral background, deep navy type, teal chart/brand, orange shortage, fine borders, generous spacing. Desktop sidebar with responsive navigation. Brand Requiem / Water intelligence. Main chart actual vs forecast, 4 metric cards, interactive allocation controls, zone table, schematic zone layout (not geographic map), model evidence panel, onboarding CSV import + mapping. Clearly label simulated zones and user-entered supply. Include training explanation and source link. No fake data, mock metrics or nonfunctional navigation/buttons. Page sections can use anchor navigation. Explicit labels and keyboard controls.
