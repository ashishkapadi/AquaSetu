"""Strict interval-volume contracts; missing measurements are never treated as zero."""
from dataclasses import dataclass
import hashlib
import numpy as np
import pandas as pd


class ValidationError(ValueError):
    pass


@dataclass
class Dataset:
    history: pd.DataFrame
    supply: pd.DataFrame
    zones: pd.DataFrame
    connections: pd.DataFrame
    weather: pd.DataFrame
    frequency: str = 'h'
    synthetic: bool = False

    @property
    def fingerprint(self):
        digest = hashlib.sha256(self.frequency.encode())
        for frame in (self.history, self.weather):
            digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
        return digest.hexdigest()[:20]


def table(frame, required, name, keys, nonnegative=()):
    frame = frame.copy()
    absent = set(required) - set(frame.columns)
    if absent:
        raise ValidationError(f'{name}: missing columns: {", ".join(sorted(absent))}.')
    if frame[list(required)].isna().any().any():
        raise ValidationError(f'{name}: missing values are unknown, not zero. Correct the source data.')
    for col in ('zone_id', 'source_zone', 'destination_zone', 'zone_name'):
        if col in frame:
            frame[col] = frame[col].astype(str).str.strip()
            if frame[col].eq('').any():
                raise ValidationError(f'{name}: {col} cannot be blank.')
    if 'timestamp' in frame:
        try:
            frame['timestamp'] = pd.to_datetime(frame.timestamp, utc=True, errors='raise', format='mixed')
        except (ValueError, TypeError) as exc:
            raise ValidationError(f'{name}: invalid timestamp. Use ISO 8601 timestamps.') from exc
        if frame.timestamp.isna().any():
            raise ValidationError(f'{name}: missing timestamp.')
    if frame.duplicated(keys).any():
        raise ValidationError(f'{name}: duplicate rows for {", ".join(keys)}.')
    for col in nonnegative:
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
        if not np.isfinite(frame[col]).all() or (frame[col] < 0).any():
            raise ValidationError(f'{name}: {col} must contain finite, nonnegative numbers.')
    return frame.sort_values(keys).reset_index(drop=True)


def cumulative_to_intervals(frame):
    """Difference readings at interval END timestamps; resets cannot be inferred."""
    frame = table(frame, ['timestamp', 'zone_id', 'meter_m3'], 'Cumulative readings',
                  ['zone_id', 'timestamp'], ['meter_m3'])
    frame['consumption_m3'] = frame.groupby('zone_id').meter_m3.diff()
    resets = frame.consumption_m3 < 0
    if resets.any():
        first = frame.loc[resets].iloc[0]
        raise ValidationError(f'Meter reset at {first.timestamp} in {first.zone_id}: interval consumption is unknown. '
                              'Reconcile reset intervals from meter records and upload interval volumes; do not use absolute differences.')
    return frame.dropna(subset=['consumption_m3'])[['timestamp', 'zone_id', 'consumption_m3']]


def validate(history, supply, zones, connections, weather=None, frequency='h', synthetic=False, allow_empty_supply=False):
    if frequency not in ('h', 'D'):
        raise ValidationError('Supported resolutions are hourly or daily; no automatic upsampling.')
    history = table(history, ['timestamp','zone_id','consumption_m3'], 'Consumption',
                    ['timestamp','zone_id'], ['consumption_m3'])
    supply = table(supply, ['timestamp','zone_id','available_supply_m3'], 'Supply',
                   ['timestamp','zone_id'], ['available_supply_m3'])
    zones = table(zones, ['zone_id','zone_name','priority_weight'], 'Zones', ['zone_id'], ['priority_weight'])
    if zones.empty or history.empty or (supply.empty and not allow_empty_supply):
        raise ValidationError('Consumption, supply and zone metadata must not be empty.')
    if (zones.priority_weight <= 0).any():
        raise ValidationError('Priority weights must be greater than zero.')
    if ('latitude' in zones) != ('longitude' in zones):
        raise ValidationError('Provide both latitude and longitude, or omit both.')
    if 'latitude' in zones:
        for col, limit in [('latitude',90),('longitude',180)]:
            zones[col] = pd.to_numeric(zones[col], errors='coerce')
            if not np.isfinite(zones[col]).all() or zones[col].abs().gt(limit).any():
                raise ValidationError(f'Zones: invalid {col}; omit coordinate columns when unavailable.')
    if 'transfer_cost' not in connections:
        connections = connections.assign(transfer_cost=0.0)
    connections = table(connections, ['source_zone','destination_zone','capacity_m3','transfer_cost'],
                        'Connections', ['source_zone','destination_zone'], ['capacity_m3','transfer_cost'])
    ids = set(zones.zone_id)
    if set(history.zone_id) != ids:
        raise ValidationError('Every metadata zone must have consumption history, with no unknown zone IDs.')
    for label, values in [('Supply',supply.zone_id), ('Connections',pd.concat([connections.source_zone,connections.destination_zone]))]:
        if set(values) - ids:
            raise ValidationError(f'{label}: unknown zone IDs: {set(values) - ids}.')
    if connections.source_zone.eq(connections.destination_zone).any():
        raise ValidationError('Self-transfers are not allowed.')
    dates = pd.date_range(history.timestamp.min(), history.timestamp.max(), freq=frequency)
    expected = pd.MultiIndex.from_product([dates, sorted(ids)], names=['timestamp','zone_id'])
    actual = pd.MultiIndex.from_frame(history[['timestamp','zone_id']])
    if not actual.equals(expected):
        raise ValidationError('History must have one observation per zone per declared interval, on a shared grid. '
                              'Missing observations are not zero. Reconcile gaps or select the correct resolution.')
    minimum = 24 * 35 if frequency == 'h' else 70
    if len(dates) < minimum:
        raise ValidationError(f'At least {minimum} complete {"hourly" if frequency == "h" else "daily"} intervals per zone are required for evaluation.')
    delta = pd.Timedelta(hours=1) if frequency == 'h' else pd.Timedelta(days=1)
    if ((supply.timestamp - dates[0]) % delta != pd.Timedelta(0)).any():
        raise ValidationError('Supply timestamps must align with the consumption interval grid.')
    if weather is None:
        weather = pd.DataFrame(columns=['timestamp','temperature','rainfall'])
    weather = table(weather, ['timestamp','temperature','rainfall'], 'Weather', ['timestamp'], ['rainfall'])
    if not weather.empty:
        weather['temperature'] = pd.to_numeric(weather.temperature, errors='coerce')
        if not np.isfinite(weather.temperature).all():
            raise ValidationError('Temperature must contain finite numeric Celsius values.')
        if not dates.isin(weather.timestamp).all():
            raise ValidationError('Weather must cover every historical interval, or omit the weather file.')
        # Future weather in the upload is deliberately excluded: it lacks an issue-time contract.
        weather = weather[weather.timestamp.isin(dates)].reset_index(drop=True)
    return Dataset(history, supply, zones, connections, weather, frequency, synthetic)


def demo(seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2026-07-01', periods=24*90, freq='h', tz='UTC')
    all_dates = pd.date_range(dates[0], periods=len(dates)+72, freq='h')
    temperature = 27 + 5*np.sin(2*np.pi*(all_dates.hour.to_numpy()-9)/24) + rng.normal(0,1,len(all_dates))
    rain = rng.choice([0.,0.,0.,0.,2.,6.],len(all_dates))
    weather = pd.DataFrame({'timestamp':all_dates,'temperature':temperature,'rainfall':rain})
    zones = pd.DataFrame({'zone_id':['N','C','E','S','W'],
        'zone_name':['Thane','Mumbai','Kalyan','Dombivli','Navi Mumbai'],
        'priority_weight':[1.,2.,1.3,1.,1.],
        'latitude':[19.2183,19.0760,19.2403,19.2183,19.0330], 'longitude':[72.9781,72.8777,73.1305,73.0865,73.0297]})
    history, supplies = [], []
    for i,z in enumerate(zones.zone_id):
        base = [95,115,135,85,100][i]
        hour = all_dates.hour.to_numpy()
        daily = 0.78 + 0.40*np.exp(-((hour-8)/3)**2) + 0.46*np.exp(-((hour-19)/3)**2)
        weekly = np.where(all_dates.dayofweek.to_numpy() >= 5, 0.85 if z=='E' else 1.08,1.)
        pattern = base*daily*weekly + 1.8*(temperature-25) - 0.8*rain
        values = np.maximum(0,pattern[:len(dates)] + rng.normal(0,4,len(dates)) + np.linspace(0,8,len(dates)))
        for offset,mult in [(int(len(dates)*0.69)+i*3,1.75),(len(dates)-50+i*2,2.4),(len(dates)-20+i,0.12)]:
            values[offset:offset+3] *= mult
        history.append(pd.DataFrame({'timestamp':dates,'zone_id':z,'consumption_m3':values.round(3)}))
        # An explicit per-interval delivery schedule, NOT repeated reservoir storage.
        future = np.maximum(0, pattern[len(dates):] + 6) * [1.35,0.72,0.84,0.82,1.48][i]
        supplies.append(pd.DataFrame({'timestamp':all_dates[len(dates):],'zone_id':z,'available_supply_m3':future.round(3)}))
    connections = pd.DataFrame([('N','C',30,1),('N','E',20,2),('W','C',25,1.5),('W','S',30,1),('W','E',15,3)],
                               columns=['source_zone','destination_zone','capacity_m3','transfer_cost'])
    return validate(pd.concat(history),pd.concat(supplies),zones,connections,weather,'h',True)
