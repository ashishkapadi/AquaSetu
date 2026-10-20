"""Artificial fixtures exercise the code only; never reported as Kaggle results."""
import json
import numpy as np
import pandas as pd
import pytest
from backend.data import prepare
from backend.forecasting import features, train, dashboard


def fixture_frame(n=1008):
    time = pd.date_range('2024-01-01', periods=n, freq='h')
    values = 120 + 30*np.sin(2*np.pi*np.arange(n)/24) + np.random.default_rng(42).normal(0,3,n)
    return pd.DataFrame({'timestamp': time, 'consumption': values})


def test_features_do_not_see_present_or_future():
    frame = fixture_frame()
    series = frame.set_index('timestamp').consumption
    original = features(series)
    changed = series.copy()
    changed.iloc[400:] = 100000
    pd.testing.assert_frame_equal(original.iloc[:401], features(changed).iloc[:401])


def test_causal_gap_fill_does_not_invent_target(tmp_path):
    frame = fixture_frame()
    frame.loc[500, 'consumption'] = np.nan
    path = tmp_path / 'history.csv'
    frame.to_csv(path, index=False)
    groups, report = prepare(path, 'timestamp', 'consumption')
    assert report['missing_hours'] == 1
    series = next(iter(groups.values()))
    assert pd.isna(series.iloc[500])
    assert features(series).iloc[501].lag_1 == series.iloc[499]


def test_training_persists_real_outputs_and_zone_shares(tmp_path):
    path = tmp_path / 'fixture.csv'
    frame = fixture_frame()
    frame['timestamp'] = frame.timestamp.dt.tz_localize('Etc/GMT-2')
    frame.to_csv(path, index=False)
    result = train(path, 'timestamp', 'consumption', None, 'fixture units', tmp_path / 'artifacts')
    assert result['source']['simulated_zones'] is True
    assert result['source']['timezone'] == 'UTC'
    assert result['source']['start'] == '2023-12-31T22:00:00Z'
    assert result['analysis']['split']['test_start'].endswith('Z')
    assert result['analysis']['zones'][0]['history'][0]['timestamp'].endswith('Z')
    assert result['metrics']['test_rows'] > 48
    assert result['metrics']['selected_mae'] >= 0
    assert len(result['zones']) == 5
    assert sum(z['share'] for z in result['zones']) == pytest.approx(1)
    for horizon in (1,6,12,24):
        response = dashboard(result, horizon)
        assert len(response['forecast']) == horizon
        assert sum(z['predicted_demand'] for z in response['zones']) == pytest.approx(sum(p['predicted'] for p in response['forecast']))
        assert pd.Timestamp(response['forecast'][0]['timestamp']) > pd.Timestamp(result['forecast_origin'])
    persisted = json.loads((tmp_path / 'artifacts' / 'dashboard.json').read_text())
    assert persisted['metrics'] == result['metrics']
    evidence = result['analysis']
    assert evidence['overall']['mae'] == pytest.approx(result['metrics']['selected_mae'])
    assert sum(z['samples'] for z in evidence['zones']) == result['metrics']['test_rows']
    assert len(evidence['zones']) == 1  # Evidence remains measured, not five fictional districts.
    for row in evidence['horizon_backtest']:
        assert row['samples'] == row['origins'] * row['hours']
        assert row['volume_mae'] >= 0
    assert 'analysis' not in dashboard(result, 1)


def test_recursive_backtest_never_passes_future_observations():
    from backend.evaluation import recursive_backtest
    series = fixture_frame().set_index('timestamp').consumption
    boundary = series.index[850]
    seen = []
    def fake_forecast(past, model, selected, hours):
        seen.append(past.index[-1])
        return [{'predicted': float(past.iloc[-1])} for _ in range(hours)]
    rows = recursive_backtest({'district': series}, {'district': None}, 'test', boundary, fake_forecast)
    assert seen == [boundary - pd.Timedelta(hours=1)] * 2
    for row in rows:
        actual = series.loc[boundary:].iloc[:row['hours']].to_numpy()
        prediction = series.loc[series.index < boundary].iloc[-1]
        assert row['mae'] == pytest.approx(np.abs(actual-prediction).mean())
        assert row['volume_mae'] == pytest.approx(abs(prediction*row['hours']-actual.sum()))


def test_numeric_id_is_not_a_date(tmp_path):
    frame = fixture_frame()
    frame['timestamp'] = np.arange(len(frame))
    path = tmp_path / 'bad.csv'
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match='numeric row IDs'):
        prepare(path, 'timestamp', 'consumption')


def test_duplicate_hours_rejected(tmp_path):
    frame = fixture_frame()
    frame.loc[1, 'timestamp'] = frame.loc[0, 'timestamp']
    path = tmp_path / 'duplicate.csv'
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match='Duplicate'):
        prepare(path, 'timestamp', 'consumption')
