"""CSV import for forecasts, with optional supply and network planning inputs."""
import io
import pandas as pd
from .data import validate, cumulative_to_intervals, ValidationError


def read_csv(content):
    try:
        return pd.read_csv(io.BytesIO(content),dtype={'zone_id':str,'source_zone':str,'destination_zone':str})
    except (ValueError,UnicodeError,pd.errors.ParserError) as exc:
        raise ValidationError('Cannot read this CSV. Use a UTF-8, comma-separated file with column headers.') from exc


def import_csvs(history_bytes,supply_bytes=None,zones_bytes=None,connections_bytes=None,
                weather_bytes=None,frequency='h',cumulative=False):
    history=read_csv(history_bytes)
    if 'zone_id' not in history or history.zone_id.isna().any():
        raise ValidationError('Consumption requires a nonempty zone_id column.')
    if cumulative:
        history=cumulative_to_intervals(history)
    ids=history.zone_id.drop_duplicates().astype(str)
    zones=read_csv(zones_bytes) if zones_bytes else pd.DataFrame({'zone_id':ids,'zone_name':ids,'priority_weight':1.})
    supply=read_csv(supply_bytes) if supply_bytes else pd.DataFrame(columns=['timestamp','zone_id','available_supply_m3'])
    connections=read_csv(connections_bytes) if connections_bytes else pd.DataFrame(columns=['source_zone','destination_zone','capacity_m3'])
    weather=read_csv(weather_bytes) if weather_bytes else None
    if weather is None and {'temperature','rainfall','timestamp'}.issubset(history.columns):
        weather=history[['timestamp','temperature','rainfall']].drop_duplicates()
        if weather.timestamp.duplicated().any():
            raise ValidationError('Weather columns must agree across zones at each timestamp, or use a separate city-wide weather CSV.')
    return validate(history,supply,zones,connections,weather,frequency,allow_empty_supply=True)
