"""Held-out diagnostics. Never used to tune or select the forecasting model."""
import numpy as np
import pandas as pd


def scores(actual, predicted, baseline):
    actual, predicted, baseline = map(np.asarray, (actual, predicted, baseline))
    error = predicted - actual
    mae = float(np.mean(np.abs(error)))
    base = float(np.mean(np.abs(baseline - actual)))
    return dict(mae=mae, rmse=float(np.sqrt(np.mean(error ** 2))),
                bias=float(np.mean(error)), baseline_mae=base,
                improvement_pct=100 * (base-mae)/base if base else 0., samples=len(actual))


def recursive_backtest(groups, models, selected, test_start, forecast):
    first = next(iter(groups.values()))
    # Fixed weekly-spaced candidates spread over the test period; no error-based selection.
    candidates = pd.date_range(test_start, first.index[-1] - pd.Timedelta(hours=23), freq='168h')
    indices = np.unique(np.linspace(0, len(candidates)-1, min(8, len(candidates)), dtype=int))
    buckets = {h: dict(y=[], p=[], b=[], volume=[], base_volume=[]) for h in (1, 6, 12, 24)}
    accepted = []
    for index in indices:
        start = candidates[index]
        end = start + pd.Timedelta(hours=23)
        # The same origins and all districts enter every horizon comparison.
        if any(s.loc[start:end].isna().any() or len(s.loc[start:end]) != 24 or
               s.loc[s.index < start].ffill(limit=6).iloc[-168:].isna().any() for s in groups.values()):
            continue
        accepted.append(start.isoformat())
        for name, series in groups.items():
            past = series.loc[series.index < start]
            y = series.loc[start:end].to_numpy()
            p = np.array([v['predicted'] for v in forecast(past, models[name], selected, 24)])
            b = np.array([v['predicted'] for v in forecast(past, None, 'Weekly seasonal baseline', 24)])
            for h, bucket in buckets.items():
                bucket['y'].extend(y[:h]); bucket['p'].extend(p[:h]); bucket['b'].extend(b[:h])
                bucket['volume'].append(abs(float(p[:h].sum()-y[:h].sum())))
                bucket['base_volume'].append(abs(float(b[:h].sum()-y[:h].sum())))
    rows = []
    for h, bucket in buckets.items():
        if bucket['y']:
            rows.append(dict(hours=h, **scores(bucket['y'], bucket['p'], bucket['b']),
                             volume_mae=float(np.mean(bucket['volume'])),
                             baseline_volume_mae=float(np.mean(bucket['base_volume'])),
                             origins=len(accepted), origin_timestamps=accepted))
    return rows
