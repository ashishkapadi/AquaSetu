from fastapi.testclient import TestClient
from backend import main


def test_untrained_and_invalid_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATA', tmp_path)
    monkeypatch.setitem(main.state, 'result', None)
    client = TestClient(main.app)
    assert client.get('/api/status').json()['ready'] is False
    assert client.get('/api/dashboard').status_code == 409
    assert client.get('/api/analysis').status_code == 409
    assert client.get('/api/zone-series?zone_id=zone-1').status_code == 409
    assert client.get('/api/dashboard?horizon=5').status_code == 422
    assert client.post('/api/allocate', json={'supply': -1}).status_code == 422
    assert client.post('/api/train', json={'filename':'../secret.csv','timestamp_column':'t','target_column':'y'}).status_code == 400


def test_upload_inspects_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATA', tmp_path)
    client = TestClient(main.app)
    content = b'timestamp,consumption\n2024-01-01 00:00:00,10\n'
    first = client.post('/api/upload', files={'file': ('test.csv', content, 'text/csv')})
    assert first.status_code == 200
    assert first.json()['columns'] == ['timestamp', 'consumption']
    second = client.post('/api/upload', files={'file': ('test.csv', content, 'text/csv')})
    assert second.json()['name'] != first.json()['name']
    assert client.post('/api/upload', files={'file': ('../outside.csv', content, 'text/csv')}).status_code == 400


def test_horizon_query_coerces_http_string(monkeypatch):
    monkeypatch.setattr(main, 'get_dashboard', lambda horizon: {'horizon': horizon})
    client = TestClient(main.app)
    for horizon in (1,6,12,24):
        response = client.get(f'/api/dashboard?horizon={horizon}')
        assert response.status_code == 200
        assert response.json()['horizon'] == horizon


def test_analysis_and_district_contract(monkeypatch):
    result = {'analysis': {'model':'fixture'}, 'source': {'unit':'m³','timezone':'UTC'},
              'zones':[{'id':'z','name':'District'}], 'zone_history':{'z':[{'actual':2}]},
              'forecast_by_zone':{'z':[{'predicted':3}]*24}}
    monkeypatch.setitem(main.state, 'result', result)
    client = TestClient(main.app)
    assert client.get('/api/analysis').json() == {'model':'fixture'}
    response = client.get('/api/zone-series?zone_id=z&horizon=6')
    assert len(response.json()['forecast']) == 6
    assert client.get('/api/zone-series?zone_id=missing').status_code == 404
    assert client.get('/api/zone-series?zone_id=z&horizon=2').status_code == 422


def test_direct_page_refresh_and_unknown_api():
    client = TestClient(main.app)
    for route in ('dashboard','forecasts','anomalies','allocation','zones','analysis','data','map','welcome','location'):
        assert client.get('/'+route).status_code == 200
        assert 'text/html' in client.get('/'+route).headers['content-type']
    assert client.get('/api/nonexistent').status_code == 404


def test_map_timeline_conserves_hourly_supply_and_uses_forecasts(monkeypatch):
    import pytest
    forecast = [{'timestamp':f'2024-01-01T{hour:02d}:00:00Z','predicted':float(hour+1)} for hour in range(24)]
    result = {'source': {'unit':'m³','timezone':'UTC'}, 'forecast_origin':'2023-12-31T23:00:00Z',
              'zones':[{'id':'z','name':'District'}], 'forecast_by_zone':{'z':forecast}}
    monkeypatch.setitem(main.state, 'result', result)
    client = TestClient(main.app)
    response = client.post('/api/map-timeline',json={'hourly_supply':12})
    assert response.status_code == 200
    frames = response.json()['frames']
    assert len(frames) == 24
    for hour, frame in enumerate(frames):
        a = frame['allocation']
        assert frame['timestamp'] == forecast[hour]['timestamp']
        assert a['total_demand'] == hour+1
        assert a['allocated'] == pytest.approx(min(12,hour+1))
        assert a['allocated']+a['unused_supply'] == pytest.approx(12)
        assert a['allocated']+a['shortage'] == pytest.approx(hour+1)
    assert frames[0]['allocation']['zones'][0]['risk'] == 'low'
    assert frames[-1]['allocation']['zones'][0]['risk'] == 'high'
    assert client.post('/api/map-timeline',json={'hourly_supply':-1}).status_code == 422
    assert client.post('/api/map-timeline',json={'hourly_supply':10,'priorities':{'unknown':5}}).status_code == 422
    monkeypatch.setitem(main.state, 'result', None)
    assert client.post('/api/map-timeline',json={'hourly_supply':10}).status_code == 409
