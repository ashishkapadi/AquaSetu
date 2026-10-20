"""Chronological demand modelling, with a seasonal baseline and honest evidence."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from .data import prepare
from .evaluation import scores, recursive_backtest

LAGS = (1, 2, 3, 24, 48, 168)


def features(series):
    # Short gaps may use earlier readings; no backward fill or future interpolation.
    past = series.ffill(limit=6)
    f = pd.DataFrame(index=series.index)
    f['hour_sin'] = np.sin(2 * np.pi * f.index.hour / 24)
    f['hour_cos'] = np.cos(2 * np.pi * f.index.hour / 24)
    f['weekday'] = f.index.dayofweek
    f['month'] = f.index.month
    for lag in LAGS:
        f[f'lag_{lag}'] = past.shift(lag)
    for window in (6, 24, 168):
        f[f'mean_{window}'] = past.shift(1).rolling(window, min_periods=window).mean()
    return f


def estimator():
    return HistGradientBoostingRegressor(max_iter=120, max_leaf_nodes=15,
                                        learning_rate=.07, l2_regularization=2,
                                        early_stopping=False, random_state=42)


def recursive_forecast(series, model, selected, hours=24):
    working = series.ffill(limit=6).copy()
    predictions = []
    for _ in range(hours):
        time = working.index[-1] + pd.Timedelta(hours=1)
        working.loc[time] = np.nan
        x = features(working.iloc[-337:]).iloc[[-1]]
        if x.isna().any(axis=None):
            raise ValueError('The most recent history has unresolved gaps. Repair data before forecasting.')
        prediction = (model.predict(x)[0] if selected == 'Gradient boosted trees'
                      else working.iloc[-169])
        prediction = max(0., float(prediction))
        working.loc[time] = prediction
        predictions.append({'timestamp': time.isoformat(), 'predicted': prediction})
    return predictions


def train(path, timestamp_column, target_column, zone_column, unit, output_dir):
    metadata_path = Path(path).with_suffix('.metadata.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
    if metadata.get('unit') and unit.strip() != metadata['unit']:
        raise ValueError(f'This prepared dataset is documented in {metadata["unit"]}. Use that unit when training.')
    groups, quality = prepare(path, timestamp_column, target_column, zone_column)
    timezone = quality.get('normalized_timezone') or metadata.get('timezone', 'source local time')
    first = next(iter(groups.values()))
    n = len(first)
    validation_start, test_start = first.index[int(n * .70)], first.index[int(n * .85)]
    records = {}
    all_v_y, all_v_ml, all_v_base = [], [], []
    for label, series in groups.items():
        x = features(series)
        usable = x.notna().all(axis=1) & series.notna()
        fit_mask = usable & (x.index < validation_start)
        val_mask = usable & (x.index >= validation_start) & (x.index < test_start)
        test_mask = usable & (x.index >= test_start)
        if fit_mask.sum() < 200 or val_mask.sum() < 48 or test_mask.sum() < 48:
            raise ValueError(f'{label}: too few usable readings after gaps and lag features; provide more continuous history.')
        model = estimator().fit(x.loc[fit_mask], series.loc[fit_mask])
        val_prediction = np.maximum(0, model.predict(x.loc[val_mask]))
        baseline = x.loc[val_mask, 'lag_168'].to_numpy()
        all_v_y.extend(series.loc[val_mask].to_numpy())
        all_v_ml.extend(val_prediction)
        all_v_base.extend(baseline)
        records[label] = (x, usable, fit_mask, val_mask, test_mask, val_prediction, baseline)
    val_ml = float(mean_absolute_error(all_v_y, all_v_ml))
    val_base = float(mean_absolute_error(all_v_y, all_v_base))
    selected = 'Gradient boosted trees' if val_ml < val_base else 'Weekly seasonal baseline'
    test_y, test_ml, test_base = [], [], []
    models, zones, forecast_by_zone, recent_anomalies = {}, [], {}, []
    fit_count = val_count = test_count = 0
    evaluation_models, zone_evidence, hourly_rows, zone_history = {}, [], [], {}
    for number, (label, series) in enumerate(groups.items()):
        x, usable, fit_mask, val_mask, test_mask, val_prediction, baseline = records[label]
        model = estimator().fit(x.loc[usable & (x.index < test_start)], series.loc[usable & (x.index < test_start)])
        pred = np.maximum(0, model.predict(x.loc[test_mask]))
        base = x.loc[test_mask, 'lag_168'].to_numpy()
        test_y.extend(series.loc[test_mask].to_numpy())
        test_ml.extend(pred)
        test_base.extend(base)
        residuals = series.loc[val_mask].to_numpy() - (val_prediction if selected == 'Gradient boosted trees' else baseline)
        threshold = max(float(np.quantile(np.abs(residuals), .99)), float(series.loc[fit_mask].median()) * .01, 1e-9)
        test_predictions = pred if selected == 'Gradient boosted trees' else base
        zone_id = f'zone-{number + 1}'
        evaluation_models[label] = model
        actuals = series.loc[test_mask]
        zone_evidence.append(dict(id=zone_id, name=label,
            **scores(actuals.to_numpy(), test_predictions, base),
            validation_model_mae=float(mean_absolute_error(series.loc[val_mask], val_prediction)),
            validation_baseline_mae=float(mean_absolute_error(series.loc[val_mask], baseline)),
            history=[dict(timestamp=t.isoformat(), actual=float(y), predicted=float(p), baseline=float(b))
                     for t,y,p,b in list(zip(actuals.index, actuals, test_predictions, base))[-168:]]))
        hourly_rows.extend(dict(hour=t.hour, error=abs(float(p-y)), base_error=abs(float(b-y)))
                           for t,y,p,b in zip(actuals.index, actuals, test_predictions, base))
        zone_history[zone_id] = [dict(timestamp=t.isoformat(), actual=float(y) if pd.notna(y) else None)
                                 for t,y in series.iloc[-72:].items()]
        for time, actual, expected in zip(series.loc[test_mask].index, series.loc[test_mask], test_predictions):
            if time >= series.index[-1] - pd.Timedelta(hours=71) and abs(float(actual) - float(expected)) > threshold:
                recent_anomalies.append(dict(timestamp=time.isoformat(), zone=label,
                    actual=float(actual), expected=float(expected), deviation=float(actual-expected), threshold=threshold))
        # A last-hour alert is computed before refitting on all the observations.
        recent_x = x.iloc[[-1]]
        if recent_x.isna().any(axis=None) or pd.isna(series.iloc[-1]):
            raise ValueError(f'{label}: the last reading or its historical inputs are missing.')
        expected_current = max(0., float(model.predict(recent_x)[0] if selected == 'Gradient boosted trees' else recent_x.lag_168.iloc[0]))
        current = float(series.iloc[-1])
        delta = current - expected_current
        final_model = estimator().fit(x.loc[usable], series.loc[usable])
        models[label] = final_model
        zone_id = f'zone-{number + 1}'
        forecast_by_zone[zone_id] = recursive_forecast(series, final_model, selected)
        zones.append(dict(id=zone_id, name=label, share=1., current_consumption=current,
                          expected_current=expected_current, anomaly=abs(delta) > threshold,
                          anomaly_direction='high' if delta > 0 else 'low',
                          anomaly_threshold=threshold, priority=1))
        fit_count += int(fit_mask.sum())
        val_count += int(val_mask.sum())
        test_count += int(test_mask.sum())
    ml_mae = float(mean_absolute_error(test_y, test_ml))
    baseline_mae = float(mean_absolute_error(test_y, test_base))
    selected_mae = ml_mae if selected == 'Gradient boosted trees' else baseline_mae
    simulated = len(zones) == 1
    hourly = pd.DataFrame(hourly_rows).groupby('hour').agg(mae=('error','mean'), baseline_mae=('base_error','mean'), samples=('error','size')).reset_index()
    analysis = dict(model=selected, unit=unit, timezone=timezone,
        split=dict(train_start=first.index[0].isoformat(), validation_start=validation_start.isoformat(),
                   test_start=test_start.isoformat(), test_end=first.index[-1].isoformat()),
        overall=scores(test_y, test_ml if selected == 'Gradient boosted trees' else test_base, test_base),
        zones=zone_evidence, hourly_errors=hourly.to_dict('records'), feature_importance=[],
        feature_importance_note='Feature importance is deferred: correlated lag inputs make independent shuffling difficult to interpret. Calendar and past consumption are inputs, not proven causes.',
        horizon_backtest=recursive_backtest(groups, evaluation_models, selected, test_start, recursive_forecast),
        horizon_backtest_note='Limited backtest: up to eight predetermined weekly origins spread across the test period. Origins with missing targets or unresolved historical gaps are excluded for every district and horizon. Models are fitted before the test period. Hourly MAE pools individual hourly errors; volume MAE measures error in total district demand over each horizon. No future observations enter recursive rollouts.',
        notes=['Overall scores weight each scored district-hour equally. Positive bias means overprediction.',
               'Held-out charts show the last up to 168 scored observations per measured district; predictions use observed past readings each hour.',
               'Test diagnostics do not select or tune the model. Final live forecasts use models refitted on all available history.',
               'These are our chronological holdout results, not the original BWDF competition scores.'],
        references=[dict(name='Shadcn Admin', url='https://github.com/satnaing/shadcn-admin', purpose='UI organization inspiration: sidebar navigation and focused pages.'),
                    dict(name='WaterFutures / BWDF', url='https://github.com/WaterFutures/wf4bwdf', purpose='Source data and reference for district-level water-demand evaluation. Our model and holdout are separate.')])
    if simulated:
        original = zones[0]
        measured_forecast = forecast_by_zone[original['id']]
        measured_history = zone_history[original['id']]
        zones, forecast_by_zone = [], {}
        for i, (label, share) in enumerate([('North', .30), ('Central', .25), ('East', .20), ('South', .15), ('West', .10)]):
            zone_id = f'zone-{i + 1}'
            zone = {**original, 'id': zone_id, 'name': label + ' · simulated', 'share': share}
            for field in ('current_consumption', 'expected_current', 'anomaly_threshold'):
                zone[field] *= share
            zones.append(zone)
            forecast_by_zone[zone_id] = [{**p, 'predicted': p['predicted'] * share} for p in measured_forecast]
            zone_history[zone_id] = [{**p, 'actual': p['actual'] * share if p['actual'] is not None else None} for p in measured_history]
    history_frame = pd.concat(groups, axis=1)
    history = history_frame.sum(axis=1, min_count=len(groups)).iloc[-72:]
    notes = [
        'Historical replay: forecasts start immediately after the last timestamp in the uploaded CSV.',
        'Supply and priority weights are operator-entered scenarios, not measured infrastructure capacity.',
        'Units are declared during import. Consumption must represent water volume within each hour; convert flow rates or cumulative meter readings first.',
        'Only consumption lags and calendar features are used. Weather is not included.',
        f'{quality["missing_hours"]} missing hourly readings; at most six hours forward-filled for features only. Missing targets excluded.',
        '99th-percentile validation error thresholds flag unusual consumption, not confirmed leaks.',
        '1-hour MAE uses observed past readings at each test origin. Longer forecasts recursively use their own predictions; a separate limited multi-hour backtest is available in Model Analysis.'
    ]
    if simulated:
        notes.append('Five illustrative zones split one measured series using fixed shares: 30%, 25%, 20%, 15%, 10%. Alerts are inherited system signals, not independently detected zone events. No geographic locations are asserted.')
    result = dict(
        source=dict(name=metadata.get('name', Path(path).name), url=metadata.get('url', ''),
                    unit=unit.strip() or 'dataset units', frequency='hourly', start=first.index[0].isoformat(),
                    end=first.index[-1].isoformat(), rows=quality['rows'], observed_zones=len(groups),
                    simulated_zones=simulated, timezone=timezone,
                    license=metadata.get('license'), notes=metadata.get('notes', []) + notes),
        forecast_origin=first.index[-1].isoformat(),
        metrics=dict(model=selected, model_mae=ml_mae, baseline_mae=baseline_mae,
                     selected_mae=selected_mae, improvement_pct=100 * (baseline_mae-selected_mae)/baseline_mae if baseline_mae else 0.,
                     validation_model_mae=val_ml, validation_baseline_mae=val_base,
                     training_rows=fit_count, validation_rows=val_count, test_rows=test_count,
                     test_start=test_start.isoformat(), test_end=first.index[-1].isoformat(),
                     evaluation='Chronological 70/15/15 split. Model chosen on validation MAE. Test scores are next-hour rolling-origin predictions with known past readings. Final forecast model refitted on all history.'),
        history=[dict(timestamp=t.isoformat(), actual=float(v) if pd.notna(v) else None) for t,v in history.items()],
        zones=zones, forecast_by_zone=forecast_by_zone, zone_history=zone_history, analysis=analysis,
        recent_anomalies=sorted(recent_anomalies, key=lambda row: row['timestamp'], reverse=True)[:20],
        explanation=['Forecast: learn consumption patterns using past readings and calendar information.',
                     'Detect: compare observed consumption with a prediction made without that observation.',
                     'Allocate: divide a shared supply in proportion to demand and operator priority, capped at demand.',
                     'Conserve: redistribution cannot remove a system-wide water deficit or guarantee pipe feasibility.'])
    if timezone == 'UTC':
        for key in analysis['split']:
            analysis['split'][key] += 'Z'
        for zone in analysis['zones']:
            for row in zone['history']:
                row['timestamp'] += 'Z'
        for row in analysis['horizon_backtest']:
            row['origin_timestamps'] = [t + 'Z' for t in row['origin_timestamps']]
        for rows in zone_history.values():
            for row in rows:
                row['timestamp'] += 'Z'
        result['forecast_origin'] += 'Z'
        for key in ('start', 'end'):
            result['source'][key] += 'Z'
        for key in ('test_start', 'test_end'):
            result['metrics'][key] += 'Z'
        for row in result['history']:
            row['timestamp'] += 'Z'
        for row in result['recent_anomalies']:
            row['timestamp'] += 'Z'
        for rows in result['forecast_by_zone'].values():
            for row in rows:
                row['timestamp'] += 'Z'
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({'models': models, 'selected': selected, 'columns': list(next(iter(records.values()))[0].columns)}, output_dir / 'model.joblib')
    temporary = output_dir / 'dashboard.tmp'
    temporary.write_text(json.dumps(result, allow_nan=False, indent=2), encoding='utf-8')
    temporary.replace(output_dir / 'dashboard.json')
    (output_dir / 'training-report.json').write_text(json.dumps(result['metrics'], indent=2), encoding='utf-8')
    return result


def dashboard(result, horizon):
    if horizon not in (1, 6, 12, 24):
        raise ValueError('Choose a 1, 6, 12 or 24 hour horizon.')
    zones = [{**z, 'predicted_demand': sum(p['predicted'] for p in result['forecast_by_zone'][z['id']][:horizon])} for z in result['zones']]
    all_forecasts = list(result['forecast_by_zone'].values())
    forecast = [dict(timestamp=all_forecasts[0][i]['timestamp'], predicted=sum(f[i]['predicted'] for f in all_forecasts)) for i in range(horizon)]
    return {k: v for k,v in result.items() if k not in ('zones','forecast_by_zone','zone_history','analysis')} | dict(
        horizon=horizon, zones=zones, forecast=forecast,
        default_supply=.8 * sum(z['predicted_demand'] for z in zones))
