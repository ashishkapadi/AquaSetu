from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


def test_dashboard_navigation_and_controls():
    with patch('smart_water.regional.fetch_report', side_effect=__import__('smart_water.live',fromlist=['LiveError']).LiveError('Test: provider unavailable')):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
    assert not app.exception
    assert len(app.get("file_uploader"))==0
    app.sidebar.radio[0].set_value("Synthetic demo").run()
    assert len(app.metric)==4
    for page in ['Live dashboard','Demand forecast','Anomaly alerts','Shortage map','Shortage prediction','Redistribution','Data & methodology','Overview']:
        app.sidebar.radio[1].set_value(page).run()
        assert not app.exception, page
    app.sidebar.radio[1].set_value('Shortage map').run()
    comparison=next(r for r in app.radio if r.label=='Map shows')
    comparison.set_value('After redistribution').run()
    assert not app.exception
    assert any(m.label=='Shortage after transfers' for m in app.metric)
    app.sidebar.radio[1].set_value('Overview').run()
    app.sidebar.radio[0].set_value('Demo CSV bundle').run()
    assert not app.exception
    assert len(app.metric)==4
    app.sidebar.radio[1].set_value('Demand forecast').run()
    assert not app.exception
    assert any('Compare with the same intervals last week' in item.value for item in app.markdown)
    app.sidebar.toggle[0].set_value(True).run()
    assert not app.exception
    app.sidebar.selectbox[2].set_value('Priority baseline').run()
    assert not app.exception
    app.sidebar.radio[1].set_value('Live dashboard').run()
    demand_before=[m.value for m in app.metric[:5]]
    available_before=next(m.value for m in app.metric if m.label=='Available supply')
    next(s for s in app.slider if s.label=='Scheduled supply available (%)').set_value(80).run()
    assert not app.exception
    assert [m.value for m in app.metric[:5]]==demand_before
    assert next(m.value for m in app.metric if m.label=='Available supply')!=available_before
    next(s for s in app.slider if s.label=='Temperature scenario shift (°C)').set_value(3.0).run()
    assert not app.exception
    assert [m.value for m in app.metric[:5]]!=demand_before
    next(r for r in app.radio if r.label=='Dashboard view').set_value('Admin allocation').run()
    assert not app.exception
    next(s for s in app.slider if s.label=='Move donor’s scheduled supply (%)').set_value(100).run()
    assert not app.exception
    assert any('increases unmet demand' in e.value for e in app.error)
    app.sidebar.radio[0].set_value('Live connection').run()
    assert not app.exception
    assert len(app.get('file_uploader'))==0
    assert any('No real data source' in warning.value for warning in app.warning)


def test_live_workflow_without_network(monkeypatch,tmp_path):
    import pandas as pd
    from smart_water.data import demo
    from smart_water.live import LiveError
    data=demo()
    shift=pd.Timestamp.now(tz='UTC').floor('h')-data.history.timestamp.max()
    for frame in [data.history,data.supply,data.weather]:
        frame['timestamp']=frame.timestamp+shift
    data.synthetic=False
    status={'source_name':'Test-only fixture','stale':False,'error':None,'key':'test-only',
            'fetched_at':str(pd.Timestamp.now(tz='UTC')),'latest_observation':str(data.history.timestamp.max())}
    monkeypatch.setenv('WATER_API_URL','https://fixture.invalid/water')
    monkeypatch.setenv('SMART_WATER_LIVE_STORE',str(tmp_path/'live.sqlite3'))
    with patch('smart_water.regional.fetch_report',side_effect=LiveError('Test unavailable')), patch('smart_water.live.sync',return_value=(data,status)):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=120).run()
        app.sidebar.radio[0].set_value('Live connection').run()
        assert not app.exception
        assert len(app.metric)==4
        assert any('Test-only fixture' in item.value for item in app.success)
        app.sidebar.radio[1].set_value('Anomaly alerts').run()
        assert not app.exception
        assert app.metric[0].value=='0'

        for page in ['Live dashboard','Demand forecast','Shortage map','Shortage prediction','Redistribution','Data & methodology','Overview']:
            app.sidebar.radio[1].set_value(page).run()
            assert not app.exception, page
        app.sidebar.radio[1].set_value('Demand forecast').run()
        app.sidebar.slider[1].set_value(3.0).run()
        assert not app.exception
        assert app.metric[2].label=='Weather scenario effect'
        assert app.metric[2].value!='+0.0 m³'
        app.sidebar.selectbox[2].set_value('Priority baseline').run()
        app.sidebar.toggle[0].set_value(True).run()
        assert not app.exception
        # Optional live inputs disappearing must preserve forecasting and explain limitations.
        data.supply=data.supply.iloc[:0]
        data.connections=data.connections.iloc[:0]
        app.sidebar.radio[1].set_value('Overview').run()
        assert not app.exception
        assert any('future supply schedule' in item.value for item in app.info)
        assert app.metric[0].label=='Predicted demand'
        app.sidebar.radio[1].set_value('Redistribution').run()
        assert not app.exception
        assert any('future supply schedule' in item.value for item in app.error)
        status['stale']=True
        app.sidebar.radio[1].set_value('Overview').run()
        assert not app.exception
        assert any('paused' in item.value for item in app.info)
