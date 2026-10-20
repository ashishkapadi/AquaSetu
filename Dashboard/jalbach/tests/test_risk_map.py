import pytest
from smart_water.data import demo,ValidationError
from smart_water.risk_map import demo_boundaries,parse_boundaries,feature_collection,area_summary
from smart_water.allocation import shortage_plan,allocate


def test_boundary_validation():
    data=demo()
    shapes=demo_boundaries(data.zones)
    payload={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'zone_id':z},'geometry':g} for z,g in shapes.items()]}
    assert parse_boundaries(payload,set(data.zones.zone_id))==shapes
    payload['features'][0]['geometry']['coordinates'][0][0]=[999,0]
    with pytest.raises(ValidationError): parse_boundaries(payload,set(data.zones.zone_id))


def test_map_risk_before_after_and_interval_balances():
    data=demo()
    f=data.supply[['timestamp','zone_id']].copy()
    f['predicted_demand']=100.
    f['upper_m3']=110.
    result,transfers=allocate(shortage_plan(f,data.supply,data.zones),data.connections)
    summary=area_summary(result,data.history,data.zones)
    assert summary.shortage_m3.sum()==pytest.approx(result.shortage_m3.sum())
    assert summary.remaining_shortage_m3.sum()<=summary.shortage_m3.sum()
    shapes=demo_boundaries(data.zones)
    for after in [False,True]:
        collection=feature_collection(summary,shapes,after)
        assert len(collection['features'])==5
        for feature in collection['features']:
            p=feature['properties']
            assert p['display_risk']==p['risk_after' if after else 'risk_before']
            assert p['latitude']==data.zones.set_index('zone_id').loc[p['zone_id'],'latitude']
            assert p['longitude']==data.zones.set_index('zone_id').loc[p['zone_id'],'longitude']
    single=result[result.timestamp==result.timestamp.min()]
    assert area_summary(single,data.history,data.zones).available_supply_m3.sum()==pytest.approx(single.available_supply_m3.sum())
