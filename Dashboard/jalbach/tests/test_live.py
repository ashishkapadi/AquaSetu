import json
import pandas as pd
import pytest
from smart_water.data import demo
from smart_water.live import LiveError,LiveStore,decode_snapshot,sync,fetch_snapshot,source_key

@pytest.fixture
def payload():
    data=demo()
    result={'source_name':'TEST FIXTURE — not real readings','units':'m3','frequency':'h','timestamp_semantics':'interval_end'}
    for name in ['history','supply','zones','connections','weather']:
        result[name]=json.loads(getattr(data,name).to_json(orient='records',date_format='iso'))
    return result


def test_decode_and_reject_future(payload):
    assert not decode_snapshot(payload,now='2026-09-29T00:00Z').synthetic
    with pytest.raises(LiveError,match='future'): decode_snapshot(payload,now='2026-08-01T00:00Z')

@pytest.mark.parametrize('field,value',[('units','litres'),('frequency','minute'),('timestamp_semantics','start'),('source_name','')])
def test_contract(payload,field,value):
    payload[field]=value
    with pytest.raises(LiveError): decode_snapshot(payload)


def test_timezone_required(payload):
    payload['history'][0]['timestamp']='2026-07-01 00:00:00'
    with pytest.raises(LiveError,match='offset'): decode_snapshot(payload)


def test_outage_no_fabrication_and_persistent_fallback(payload,tmp_path):
    store=LiveStore(tmp_path/'live.db')
    def failed(url,token): raise LiveError('Unavailable')
    with pytest.raises(LiveError): sync('https://test.example/data',store,fetcher=failed)
    data,status=sync('https://test.example/data',store,now='2026-09-29T00:00Z',fetcher=lambda u,t:payload)
    assert not status['stale']
    same,status=sync('https://test.example/data',LiveStore(tmp_path/'live.db'),now='2026-09-29T01:00Z',fetcher=failed)
    assert status['stale'] and status['error']=='Unavailable'
    assert same.fingerprint==data.fingerprint
    with pytest.raises(LiveError): sync('https://another.example/data',store,fetcher=failed)


def test_stale_even_when_fetch_succeeds(payload,tmp_path):
    _,status=sync('https://test.example',LiveStore(tmp_path/'live.db'),now='2026-10-10T00:00Z',fetcher=lambda u,t:payload)
    assert status['stale']


def test_forecast_archive_excludes_hindsight(tmp_path):
    store=LiveStore(tmp_path/'live.db')
    forecast=pd.DataFrame({'timestamp':pd.to_datetime(['2026-10-01T10:00Z','2026-10-01T11:00Z']),
                           'zone_id':['A','A'],'predicted_demand':[10.,10.]})
    bundle={'calibration':{('Random forest','A'):{'alert':5.,'band':3.}}}
    store.record_forecasts('s',forecast,bundle,'Random forest',now='2026-10-01T10:30Z')
    observations=forecast.rename(columns={'predicted_demand':'consumption_m3'}).copy()
    observations['consumption_m3']=30.
    monitored=store.monitored('s',observations,'Random forest')
    assert len(monitored)==1
    assert monitored.timestamp.iloc[0]==pd.Timestamp('2026-10-01T11:00Z')
    assert monitored.severity.iloc[0]=='High'
    assert store.monitored('other',observations,'Random forest').empty


def test_http_fetch_and_redacted_errors(payload):
    class Response:
        status_code=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def iter_content(self,size): yield json.dumps(payload).encode()
    def get(url,**kwargs):
        assert kwargs['allow_redirects'] is False
        assert kwargs['timeout']==(5,15)
        assert kwargs['headers']['Authorization']=='Bearer server-secret'
        return Response()
    assert fetch_snapshot('https://test.example/data','server-secret',get)==payload
    with pytest.raises(LiveError,match='HTTPS'): fetch_snapshot('http://remote.example/data',get=get)


def test_regional_uses_observation_date_not_title():
    from smart_water.regional import parse_report
    html='<title>Today 11 Oct 2026</title><main>Report as of 1 Oct 2026 at 06:00 Stored 13,93,939 ML Million Litres Capacity 14,47,363 ML</main>'
    result=parse_report(html,'Mumbai',now='2026-10-11T06:00Z')
    assert result['reported_at'].startswith('2026-10-01')
    assert result['stale']
    assert result['stored_ml']==1393939


def test_regional_does_not_guess_missing_data():
    from smart_water.regional import parse_report
    with pytest.raises(LiveError,match='date'): parse_report('<h1>Today 11 Oct 2026</h1>','Mumbai')
    with pytest.raises(LiveError,match='layout'): parse_report('Data as of 1 Oct 2026','Thane')
    result=parse_report('Data as of 11 Aug 2026 Stored 3,38,840 / 3,38,840 ML','Kalyan–Dombivli',now='2026-10-11T06:00Z')
    assert result['percent_full']==100 and result['stale']

@pytest.mark.parametrize('omit',[True,False])
def test_consumption_only_live_feed(payload,omit):
    for field in ('supply','connections','weather'):
        if omit:
            payload.pop(field)
        else:
            payload[field]=[]
    data=decode_snapshot(payload)
    assert not data.history.empty
    assert data.supply.empty and data.connections.empty and data.weather.empty
    assert not data.synthetic


def test_optional_live_input_still_validated(payload):
    payload['supply']=[{'timestamp':'2026-09-29T01:00Z','zone_id':'A','available_supply_m3':-1}]
    with pytest.raises(LiveError):
        decode_snapshot(payload)
    payload.pop('supply')
    payload.pop('zones')
    with pytest.raises(LiveError,match='zones array'):
        decode_snapshot(payload)
