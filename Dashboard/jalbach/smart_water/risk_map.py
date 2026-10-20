"""Area geometry and interval-safe summaries for the shortage map."""
import math
import pandas as pd
from .data import ValidationError

COLORS={'None':[8,126,139], 'Low':[220,164,28], 'Medium':[240,130,20], 'High':[190,35,40]}


def area_summary(result, history, zones):
    totals=result.groupby('zone_id',as_index=False)[['predicted_demand','planned_demand','available_supply_m3',
        'shortage_m3','remaining_shortage_m3','received_m3','sent_m3']].sum()
    for col,label in [('shortage_pct','risk_before'),('remaining_shortage_pct','risk_after')]:
        risk_col='risk' if col=='shortage_pct' else 'risk_after'
        worst=result.sort_values(col).groupby('zone_id').tail(1)[['zone_id',risk_col]].rename(columns={risk_col:label})
        totals=totals.merge(worst,on='zone_id')
    latest=history.sort_values('timestamp').groupby('zone_id').tail(1)[['zone_id','consumption_m3']].rename(columns={'consumption_m3':'latest_observed_m3'})
    return zones.merge(totals,on='zone_id').merge(latest,on='zone_id')


def demo_boundaries(zones):
    # Illustrative service areas only; never inferred for real providers.
    return {row.zone_id:{'type':'Polygon','coordinates':[[
        [row.longitude+.013*math.cos(i*math.pi/3),row.latitude+.011*math.sin(i*math.pi/3)]
        for i in range(6)]+[[row.longitude+.013,row.latitude]]]} for row in zones.itertuples()}


def parse_boundaries(payload, zone_ids):
    if not isinstance(payload,dict) or payload.get('type')!='FeatureCollection' or not isinstance(payload.get('features'),list):
        raise ValidationError('Use a GeoJSON FeatureCollection with Polygon or MultiPolygon features.')
    result={}
    for feature in payload['features']:
        try:
            zone=str(feature['properties']['zone_id'])
            geometry=feature['geometry']
            if geometry['type'] not in ('Polygon','MultiPolygon'):
                raise ValueError()
            polygons=[geometry['coordinates']] if geometry['type']=='Polygon' else geometry['coordinates']
            if not polygons:
                raise ValueError()
            for polygon in polygons:
                if not polygon:
                    raise ValueError()
                for ring in polygon:
                    if len(ring)<4 or ring[0]!=ring[-1]:
                        raise ValueError()
                    for point in ring:
                        if len(point)!=2 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in point) or abs(point[0])>180 or abs(point[1])>90:
                            raise ValueError()
            if zone not in zone_ids or zone in result:
                raise ValueError()
            result[zone]=geometry
        except (KeyError,TypeError,ValueError,IndexError):
            raise ValidationError('Each feature needs a unique known zone_id and closed longitude/latitude rings in WGS84.')
    if set(result)!=set(zone_ids):
        raise ValidationError('Provide exactly one boundary feature for every zone, using matching zone_id values.')
    return result


def feature_collection(summary, geometries, after=False):
    features=[]
    for row in summary.to_dict('records'):
        risk=row['risk_after' if after else 'risk_before']
        props={k:round(v,1) if isinstance(v,float) and k not in ('latitude','longitude') else v for k,v in row.items()}
        props.update(color=COLORS[risk]+[255],fill=COLORS[risk]+[55],display_risk=risk)
        features.append({'type':'Feature','geometry':geometries[row['zone_id']],'properties':props})
    return {'type':'FeatureCollection','features':features}
