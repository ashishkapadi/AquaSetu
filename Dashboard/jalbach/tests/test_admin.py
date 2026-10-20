import pandas as pd
import pytest
from smart_water.admin import move_supply,coverage
from smart_water.allocation import shortage_plan
from smart_water.data import ValidationError


def test_manual_allocation_budget_capacity_and_donor_harm():
    t=pd.Timestamp('2026-01-01',tz='UTC')
    supply=pd.DataFrame({'timestamp':[t,t],'zone_id':['A','B'],'available_supply_m3':[100.,0.]})
    edge=pd.DataFrame({'source_zone':['A'],'destination_zone':['B'],'capacity_m3':[40.]})
    changed,moves=move_supply(supply,edge,'A','B',80)
    assert list(changed.available_supply_m3)==[60.,40.]
    assert changed.available_supply_m3.sum()==100
    assert moves.moved_m3.iloc[0]==40
    assert list(supply.available_supply_m3)==[100.,0.]
    f=pd.DataFrame({'timestamp':[t,t],'zone_id':['A','B'],'predicted_demand':[90.,60.],'upper_m3':[95.,65.]})
    zones=pd.DataFrame({'zone_id':['A','B'],'zone_name':['A','B'],'priority_weight':[1.,1.]})
    summary=coverage(shortage_plan(f,changed,zones)).set_index('zone_id')
    assert summary.loc['A','shortage_m3']==30
    assert summary.loc['B','shortage_m3']==20
    assert summary.loc['A','demand_covered_pct']==pytest.approx(100*60/90)
    with pytest.raises(ValidationError): move_supply(supply,edge,'B','A',20)


def test_manual_allocation_only_selected_interval():
    t=pd.Timestamp('2026-01-01',tz='UTC')
    u=t+pd.Timedelta(hours=1)
    s=pd.DataFrame({'timestamp':[t,t,u,u],'zone_id':['A','B','A','B'],'available_supply_m3':[100.,0.,100.,0.]})
    e=pd.DataFrame({'source_zone':['A'],'destination_zone':['B'],'capacity_m3':[50.]})
    updated,_=move_supply(s,e,'A','B',20,t)
    assert list(updated.available_supply_m3)==[80.,20.,100.,0.]
