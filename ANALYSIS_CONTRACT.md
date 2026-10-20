# Page refactor and analysis contract

Preserve existing APIs. Add clean frontend routes `/`, `/forecasts`, `/anomalies`, `/allocation`, `/zones`, `/analysis`, `/data`. Parent will support server-side refresh on these routes. Pages should render separate views, not scroll anchors. Support old #evidence -> /analysis links. React Router is fine. Shared state preserves current supply, priority and horizon between pages.

UI reference: https://github.com/satnaing/shadcn-admin (MIT): use its sidebar + per-page header + focused content organization as inspiration; no wholesale template migration. Retain Requiem's teal/navy visual direction, legible font sizes, responsive navigation with accessible names. Model-analysis reference: https://github.com/WaterFutures/wf4bwdf — documented per-DMA evaluation and seasonal baseline; our holdout is separate from the original competition.

## GET /api/analysis

Returns actual cached training evidence (409 if no model; if older artifact no analysis, report retraining required):

```
{
  model: string, unit: string, timezone: string,
  split: {train_start, validation_start, test_start, test_end},
  overall: {mae, rmse, bias, baseline_mae, improvement_pct, samples},
  zones: [{id, name, mae, rmse, bias, baseline_mae, improvement_pct, samples,
    validation_model_mae, validation_baseline_mae,
    history: [{timestamp, actual, predicted, baseline}]}],
  hourly_errors: [{hour, mae, baseline_mae, samples}],
  feature_importance: [{feature, label, mae_increase}],
  feature_importance_note: string,
  horizon_backtest: [{hours, mae, baseline_mae, improvement_pct, samples, origins}],
  horizon_backtest_note: string,
  notes: string[],
  references: [{name,url,purpose}]
}
```

`history` is the last up to168 scored test-hour observations per measured district, from models trained before test_start, not fitted on these targets. Plot selected district's actual, predicted and weekly baseline; show datetime UTC. Overall MAE is microaverage over district-hour rows; per-zone scores needn't equal it by simple mean if counts differ. Bias positive means overprediction. RMSE penalizes large errors.

Feature importance is deferred following statistical review. The array is empty and the note explains correlated inputs; do not render a fabricated importance chart.

Horizon backtest: fixed pre-test trained models, up to8 predetermined weekly origins in the test period, identical eligible origins across1/6/12/24h, no actual future demand injected within each rollout. MAE pools individual future hourly errors through each horizon, not total daily-volume errors. Separate this limited sample from the full next-hour test MAE; show sample/origin counts and note. No fabricated/default metric values.

## GET /api/zone-series?zone_id=zone-1&horizon=1|6|12|24

Returns `{id,name,history:[{timestamp,actual}],forecast:[{timestamp,predicted}],unit,timezone}` for selected district, last72h history. 404 unknown zone. Existing aggregate dashboard retains history/forecast and all metrics. Forecast page can select All districts (existing data) or individual zone via this endpoint.

All APIs return loading/error states cleanly; stale fetches ignored on rapid selection or navigation. Analysis fetches once then refreshes after successful retraining/manual refresh. Overview should summarize demand/supply/shortage/current alerts plus links to separate pages, not repeat fulltables. Data page owns import/retrain and source details. Allocation page owns supply slider and priorities (or convenient link to Zones). Anomaly page owns current/recent alerts. Analysis page owns evidence, per-zone metric table, selected-district heldout plot, per-hour error plot, validation feature-importance display and clearly qualified multi-hour backtest. Reasonable compact table/bar views are fine; no false feature contribution percentages.
