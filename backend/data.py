"""Strict, explicit CSV mapping; never invent timestamps, units, or zones."""
from pathlib import Path
import json
import numpy as np
import pandas as pd


def read_csv(path, nrows=None):
    return pd.read_csv(path, sep=None, engine='python', nrows=nrows)


def inspect_csv(path):
    frame = read_csv(path, nrows=5)
    metadata_path = Path(path).with_suffix('.metadata.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
    return {'name': Path(path).name, 'columns': [str(c) for c in frame.columns],
            'unit': metadata.get('unit', 'dataset units'),
            'rows_preview': len(frame),
            'preview': frame.astype(object).where(pd.notna(frame), None).to_dict('records')}


def prepare(path, timestamp_column, target_column, zone_column=None):
    raw = read_csv(path)
    if len(raw) > 500_000:
        raise ValueError('Please use a CSV of at most 500,000 rows for this local demo.')
    columns = [timestamp_column, target_column] + ([zone_column] if zone_column else [])
    if len(columns) != len(set(columns)):
        raise ValueError('Timestamp, consumption and zone must be different columns.')
    if any(c not in raw.columns for c in columns):
        raise ValueError('A selected column is not present in the CSV.')
    if pd.api.types.is_numeric_dtype(raw[timestamp_column]):
        raise ValueError('Timestamp must contain real dates and hours, not numeric row IDs. Convert documented epoch timestamps to ISO dates first.')
    timestamps = pd.to_datetime(raw[timestamp_column], errors='coerce', format='mixed')
    if timestamps.isna().any():
        raise ValueError('Some timestamps could not be parsed. Use unambiguous ISO dates: YYYY-MM-DD HH:MM:SS.')
    normalized_timezone = None
    try:
        if timestamps.dt.tz is not None:
            timestamps = timestamps.dt.tz_convert('UTC').dt.tz_localize(None)
            normalized_timezone = 'UTC'
    except AttributeError as exc:
        raise ValueError('Use a consistent timezone in the timestamp column.') from exc
    if ((timestamps.dt.minute != 0) | (timestamps.dt.second != 0)).any():
        raise ValueError('This model expects hourly observations aligned to the hour. Aggregate documented sub-hourly volumes before importing.')
    values = pd.to_numeric(raw[target_column], errors='coerce')
    if (raw[target_column].notna() & values.isna()).any():
        raise ValueError('Consumption contains nonnumeric text. Clean it before training.')
    if np.isinf(values).any() or (values.dropna() < 0).any():
        raise ValueError('Consumption must be finite and nonnegative.')
    if zone_column and raw[zone_column].isna().any():
        raise ValueError('Zone labels cannot be blank.')
    zone = raw[zone_column].astype(str) if zone_column else pd.Series('Measured system', index=raw.index)
    table = pd.DataFrame({'timestamp': timestamps, 'actual': values, 'zone': zone})
    if table.duplicated(['timestamp', 'zone']).any():
        raise ValueError('Duplicate timestamp/zone pairs found. Aggregate measurements appropriately before importing.')
    if table.zone.nunique() > 30:
        raise ValueError('Use at most 30 zones for the hackathon demo.')
    groups = {}
    for label, rows in table.groupby('zone', sort=False):
        series = rows.set_index('timestamp').actual.sort_index()
        if series.notna().sum() < 672:
            raise ValueError(f'{label}: at least 28 days (672 readings) of hourly history are required.')
        expected = pd.date_range(series.index.min(), series.index.max(), freq='h')
        if len(expected) > 500_000:
            raise ValueError('The date range is too large; check the timestamp format.')
        series = series.reindex(expected)
        if series.isna().mean() > .15:
            raise ValueError(f'{label}: more than 15% of hourly observations are missing. Check frequency and data quality.')
        groups[str(label)] = series
    starts = {s.index[0] for s in groups.values()}
    ends = {s.index[-1] for s in groups.values()}
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError('All zones must cover the same start and end hours. Trim to a common period before training.')
    return groups, {'rows': len(raw), 'missing_hours': int(sum(s.isna().sum() for s in groups.values())),
                    'normalized_timezone': normalized_timezone,
                    'ignored_columns': [str(c) for c in raw.columns if c not in columns]}
