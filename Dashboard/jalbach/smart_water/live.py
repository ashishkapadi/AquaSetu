"""Live REST snapshots, durable last-good data, and forecasts issued before observations.

No synthetic fallback. A provider adapter must supply the documented interval contract.
"""
import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
import pandas as pd
import requests
from .data import validate, ValidationError


class LiveError(ValueError):
    pass


def utc_now():
    return pd.Timestamp.now(tz='UTC')


def source_key(url):
    return hashlib.sha256(url.encode()).hexdigest()


def fetch_snapshot(url,token='',get=None):
    parsed=urlsplit(url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise LiveError('Enter a valid API URL without embedded credentials or fragments.')
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1')):
        raise LiveError('Use HTTPS for the provider API. HTTP is supported only for a local gateway.')
    headers={'Accept':'application/json'}
    if token:
        headers['Authorization']='Bearer '+token
    get=get or requests.get
    try:
        with get(url,headers=headers,timeout=(5,15),allow_redirects=False,stream=True) as response:
            if response.status_code!=200:
                raise LiveError(f'Provider returned HTTP {response.status_code}. Check access and endpoint configuration.')
            body=bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body)>25*1024*1024:
                    raise LiveError('Snapshot exceeds 25 MB. Configure a bounded rolling history window.')
            try:
                return json.loads(body)
            except (ValueError,UnicodeError) as exc:
                raise LiveError('Provider did not return valid JSON.') from exc
    except requests.RequestException as exc:
        # Do not echo URLs, response bodies, headers or tokens into UI errors.
        raise LiveError('Cannot reach the provider API. Check connectivity, TLS and credentials; automatic retry occurs on the next refresh.') from exc


def decode_snapshot(payload,now=None):
    now=utc_now() if now is None else pd.Timestamp(now)
    if not isinstance(payload,dict):
        raise LiveError('API response must be a JSON object.')
    if payload.get('units')!='m3' or payload.get('timestamp_semantics')!='interval_end':
        raise LiveError('Provider must declare units="m3" and timestamp_semantics="interval_end".')
    if payload.get('frequency') not in ('h','D'):
        raise LiveError('Provider must declare frequency="h" or "D". Do not fabricate hourly data from daily readings.')
    if not isinstance(payload.get('source_name'),str) or not payload['source_name'].strip():
        raise LiveError('Provider must identify source_name.')
    frames={}
    columns={'history':['timestamp','zone_id','consumption_m3'],
             'supply':['timestamp','zone_id','available_supply_m3'],
             'zones':['zone_id','zone_name','priority_weight'],
             'connections':['source_zone','destination_zone','capacity_m3']}
    for name,required in columns.items():
        rows=payload.get(name, [] if name in ('supply','connections') else None)
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
            raise LiveError(f'Provider must supply a {name} array of records.')
        frames[name]=pd.DataFrame(rows) if rows else pd.DataFrame(columns=required)
    weather=payload.get('weather')
    if weather is not None and (not isinstance(weather,list) or any(not isinstance(row,dict) for row in weather)):
        raise LiveError('Weather must be an array of records when supplied.')
    # Live timestamps must explicitly identify timezone, unlike legacy CSV inputs.
    for name in ('history','supply'):
        if 'timestamp' in frames[name]:
            for value in frames[name].timestamp:
                try:
                    stamp=pd.Timestamp(value)
                    if pd.isna(stamp) or stamp.tzinfo is None:
                        raise ValueError()
                except (ValueError,TypeError):
                    raise LiveError(f'{name}: use ISO timestamps with Z or an explicit UTC offset.')
    try:
        data=validate(frames['history'],frames['supply'],frames['zones'],frames['connections'],
                      pd.DataFrame(weather) if weather else None,payload['frequency'],allow_empty_supply=True)
    except ValidationError as exc:
        raise LiveError(str(exc)) from exc
    if data.history.timestamp.max()>now:
        raise LiveError('Consumption includes a future or incomplete interval. Supply only completed observations.')
    return data


class LiveStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS snapshots (source TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)')
            db.execute('''CREATE TABLE IF NOT EXISTS forecasts (
                source TEXT, model TEXT, timestamp TEXT, zone_id TEXT, origin TEXT,
                expected REAL, threshold_m3 REAL, band_m3 REAL,
                PRIMARY KEY(source,model,timestamp,zone_id,origin))''')

    def connect(self):
        return sqlite3.connect(self.path,timeout=20)

    def store(self,key,payload,now):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?,?)',(key,json.dumps(payload),str(now)))

    def latest(self,key):
        with self.connect() as db:
            row=db.execute('SELECT payload,fetched_at FROM snapshots WHERE source=?',(key,)).fetchone()
        return (json.loads(row[0]),pd.Timestamp(row[1])) if row else (None,None)

    def record_forecasts(self,key,forecast,bundle,model,now=None):
        now=utc_now() if now is None else pd.Timestamp(now)
        rows=[]
        for row in forecast.itertuples():
            if row.timestamp>now:
                calibration=bundle['calibration'][(model,row.zone_id)]
                rows.append((key,model,row.timestamp.isoformat(),row.zone_id,now.isoformat(),
                             row.predicted_demand,calibration['alert'],calibration['band']))
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO forecasts SELECT ?,?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM forecasts WHERE source=? AND model=? AND timestamp=? AND zone_id=?)', [row+row[:4] for row in rows])

    def monitored(self,key,history,model):
        with self.connect() as db:
            saved=pd.read_sql_query('SELECT * FROM forecasts WHERE source=? AND model=?',db,params=(key,model))
        if saved.empty:
            return saved
        saved['timestamp']=pd.to_datetime(saved.timestamp,utc=True)
        saved['origin']=pd.to_datetime(saved.origin,utc=True)
        # Earliest issued prediction per target. Ignore later reruns and hindsight estimates.
        saved=saved[saved.origin<saved.timestamp].sort_values('origin').drop_duplicates(['timestamp','zone_id'])
        compared=saved.merge(history.rename(columns={'consumption_m3':'actual'}),on=['timestamp','zone_id'],how='inner')
        compared['residual']=compared.actual-compared.expected
        compared['severity']='Normal'
        compared.loc[compared.residual.abs()>compared.threshold_m3,'severity']='Medium'
        compared.loc[compared.residual.abs()>2*compared.threshold_m3,'severity']='High'
        compared['explanation']=compared.residual.map(lambda x:'Unusually high usage: investigate demand, possible leakage or sensor issues.' if x>0 else 'Unusually low usage: investigate interruption, changed activity or sensor issues.')
        return compared


def sync(url,store,token='',now=None,fetcher=fetch_snapshot):
    now=utc_now() if now is None else pd.Timestamp(now)
    key=source_key(url)
    error=None
    try:
        payload=fetcher(url,token)
        data=decode_snapshot(payload,now)
        store.store(key,payload,now)
        fetched_at=now
    except LiveError as exc:
        error=str(exc)
        payload,fetched_at=store.latest(key)
        if payload is None:
            raise LiveError(error) from exc
        data=decode_snapshot(payload,now)
    interval=pd.Timedelta(hours=1) if data.frequency=='h' else pd.Timedelta(days=1)
    age=now-data.history.timestamp.max()
    stale=age>interval*2 or error is not None
    return data,{'source_name':payload['source_name'],'fetched_at':str(fetched_at),
                 'latest_observation':str(data.history.timestamp.max()),'age_minutes':age.total_seconds()/60,
                 'stale':stale,'error':error,'key':key}
