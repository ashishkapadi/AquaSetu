"""Reproducible ingestion of the official open BWDF multi-district benchmark."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlretrieve
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'waterfutures-original'
RAW.mkdir(parents=True, exist_ok=True)
BASE = 'https://raw.githubusercontent.com/WaterFutures/wf4bwdf/main/src/wf4bwdf/data/'
for filename in ('InflowData.xlsx', 'WeatherData.xlsx'):
    target = RAW / filename
    if not target.exists():
        urlretrieve(BASE + filename, target)

raw = pd.read_excel(RAW / 'InflowData.xlsx')
timestamps = pd.DatetimeIndex(pd.to_datetime(raw.iloc[:, 0], format='%d/%m/%Y %H:%M'))
timestamps = timestamps.tz_localize('Europe/Rome', ambiguous='infer').tz_convert('UTC')
if timestamps.duplicated().any():
    raise ValueError('Duplicate UTC timestamps in source; inspect before continuing.')
labels = ['Hospital', 'Rural residential A', 'Rural residential B', 'Suburban mixed',
          'Near-centre mixed', 'Sports and offices', 'Near-centre residential',
          'City centre', 'Port industrial A', 'Port industrial B']
records = []
for i, label in enumerate(labels, start=1):
    expected_column = f'DMA {i} (L/s)'
    if expected_column not in raw:
        raise ValueError(f'Source schema changed: missing {expected_column}')
    records.append(pd.DataFrame({'timestamp': timestamps.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                 'consumption_m3': pd.to_numeric(raw[expected_column], errors='raise') * 3.6,
                                 'zone': f'DMA {i} · {label}'}))
long = pd.concat(records, ignore_index=True)
path = ROOT / 'data' / 'waterfutures_hourly.csv'
long.to_csv(path, index=False)
metadata = {
    'name': 'Water-Futures · BWDF',
    'url': 'https://github.com/WaterFutures/wf4bwdf',
    'unit': 'm³',
    'timezone': 'UTC',
    'license': 'CC BY 4.0 (dataset); MIT (reference implementation)',
    'notes': [
        'Real district inflow measurements from the Battle of Water Demand Forecasting benchmark, made available by Water-Futures. These are not Bengaluru or Gangtok readings.',
        'Source hourly mean flows (L/s) converted to hourly volume (m³) by multiplying by 3.6. Inflow is used as a district-demand proxy and may include network losses.',
        'CET/CEST source timestamps localized to Europe/Rome, then converted to UTC. Repeated daylight-saving hours are preserved as distinct UTC observations.',
        'District labels describe the published service-area categories. Geographic locations and pipe connectivity are not asserted.',
        'Dataset attribution: Alvisi et al. (2025), Battle of Water Demand Forecasting, doi:10.1061/JWRMD5.WRENG-6887; distributed by Water-Futures under CC BY 4.0.',
        'This app uses its own chronological holdout, not the original competition evaluation weeks; scores are not competition leaderboard results.'
    ],
    'raw_files': {name: {'url': BASE + name, 'sha256': hashlib.sha256((RAW/name).read_bytes()).hexdigest()}
                  for name in ('InflowData.xlsx', 'WeatherData.xlsx')}
}
path.with_suffix('.metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Prepared {len(long):,} rows across {len(labels)} measured districts.')
print(f'Hourly timestamps: {len(timestamps):,}; missing measured values: {long.consumption_m3.isna().sum():,}.')
print('Training file:', path)
