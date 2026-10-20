"""Budget-conserving manual allocation scenarios. Never sends control commands."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from .allocation import shortage_plan, allocate
from .data import ValidationError


def move_supply(schedule, connections, donor, recipient, percent, timestamp=None):
    if donor==recipient or not np.isfinite(percent) or not 0<=percent<=100:
        raise ValidationError('Choose different areas and a percentage from 0 to 100.')
    edge=connections[(connections.source_zone==donor)&(connections.destination_zone==recipient)]
    if len(edge)!=1:
        raise ValidationError('A declared direct connection is required for this allocation.')
    cap=float(edge.iloc[0].capacity_m3)
    updated=schedule.copy()
    changes=[]
    selected=updated if timestamp is None else updated[updated.timestamp==timestamp]
    for t in selected.timestamp.unique():
        source=updated.index[(updated.timestamp==t)&(updated.zone_id==donor)]
        target=updated.index[(updated.timestamp==t)&(updated.zone_id==recipient)]
        if len(source)!=1 or len(target)!=1:
            raise ValidationError('Both areas need exactly one supply record per selected interval.')
        requested=float(updated.loc[source[0],'available_supply_m3'])*percent/100
        amount=min(requested,cap)
        updated.loc[source[0],'available_supply_m3']-=amount
        updated.loc[target[0],'available_supply_m3']+=amount
        changes.append({'timestamp':t,'source_zone':donor,'destination_zone':recipient,
                        'requested_m3':requested,'moved_m3':amount,'capacity_m3':cap})
    if not np.allclose(schedule.groupby('timestamp').available_supply_m3.sum(),updated.groupby('timestamp').available_supply_m3.sum()):
        raise RuntimeError('Scenario must conserve supply in every interval.')
    return updated,pd.DataFrame(changes)


def coverage(plan):
    rows=[]
    for zone,g in plan.groupby('zone_id'):
        met=np.minimum(g.available_supply_m3,g.planned_demand).sum()
        demand=g.planned_demand.sum()
        failures=g[g.shortage_m3>1e-6]
        rows.append({'zone_id':zone,'zone_name':g.zone_name.iloc[0],
            'predicted_demand_m3':g.predicted_demand.sum(),'planning_demand_m3':demand,
            'supply_m3':g.available_supply_m3.sum(),'shortage_m3':g.shortage_m3.sum(),
            'demand_covered_pct':100*met/demand if demand>0 else 100.,
            'shortage_intervals':len(failures),
            'first_shortage_UTC':str(failures.timestamp.min()) if len(failures) else 'None',
            'status':'Shortage expected' if len(failures) else 'Demand covered'})
    return pd.DataFrame(rows)


def render_admin(data,forecast,result,planning_error,conservative,method,medium,high):
    st.subheader('Admin allocation simulator')
    st.caption('Decision-support view, not an authenticated admin account. Changes remain a simulation; no pumps, valves or provider records are changed.')
    if planning_error:
        st.warning(planning_error)
        return
    if data.connections.empty:
        st.info('Add declared direct connections and capacities to simulate reallocations between areas.')
        return
    st.write('Choose which area gives up supply and which receives it. The total water budget stays fixed, and every area’s coverage is recalculated using the current forecast.')
    names=data.zones.set_index('zone_id').zone_name.to_dict()
    a,b=st.columns(2)
    donor=a.selectbox('Take supply from',sorted(data.connections.source_zone.unique()),format_func=lambda z:names[z])
    recipient=b.selectbox('Allocate supply to',sorted(data.connections.loc[data.connections.source_zone==donor,'destination_zone'].unique()),format_func=lambda z:names[z])
    period=st.selectbox('Allocation period',['Entire forecast']+list(forecast.timestamp.drop_duplicates().sort_values()),format_func=str)
    percent=st.slider('Move donor’s scheduled supply (%)',0,100,0,5,
        help='Percentage of the donor’s supply per selected interval, capped by the declared connection capacity. Moving too much may create a donor shortage.')
    schedule=result[['timestamp','zone_id','available_supply_m3']].copy().reset_index(drop=True)
    updated,moves=move_supply(schedule,data.connections,donor,recipient,percent,None if isinstance(period,str) else period)
    before=shortage_plan(forecast,schedule,data.zones,conservative,medium,high)
    after=shortage_plan(forecast,updated,data.zones,conservative,medium,high)
    old=coverage(before)
    summary=coverage(after).merge(old[['zone_id','supply_m3','shortage_m3']],on='zone_id',suffixes=('','_before'))
    summary['supply_change_m3']=summary.supply_m3-summary.supply_m3_before
    summary['shortage_change_m3']=summary.shortage_m3-summary.shortage_m3_before
    summary=summary.sort_values(['shortage_m3','zone_id'],ascending=[False,True])
    a,b,c=st.columns(3)
    a.metric('Fixed supply budget',f'{schedule.available_supply_m3.sum():,.1f} m³')
    b.metric('Supply reassigned',f'{moves.moved_m3.sum():,.1f} m³')
    c.metric('Areas with shortage',int((summary.shortage_intervals>0).sum()),delta=int((summary.shortage_intervals>0).sum()-(old.shortage_intervals>0).sum()),delta_color='inverse')
    if (moves.requested_m3>moves.moved_m3+1e-6).any():
        st.info('The requested allocation exceeds connection capacity in some intervals. The simulation caps each interval at that capacity.')
    harmed=summary[summary.shortage_change_m3>1e-6]
    if not harmed.empty:
        st.error('This decision increases unmet demand in: '+', '.join(harmed.zone_name)+'. Review the trade-off before adopting a plan.')
    st.caption('Baseline: current scheduled supply after the sidebar supply adjustment, before automatic redistribution. Coverage sums demand served per interval; surplus in a different hour does not cancel a shortage. Coverage is not a health or survival assessment.')
    st.dataframe(summary,hide_index=True,use_container_width=True)
    plot=summary.melt(id_vars='zone_name',value_vars=['shortage_m3_before','shortage_m3'],var_name='Scenario',value_name='Unmet demand (m³)')
    st.plotly_chart(px.bar(plot,x='zone_name',y='Unmet demand (m³)',color='Scenario',barmode='group',color_discrete_map={'shortage_m3_before':'#a6afc4','shortage_m3':'#00649a'}),use_container_width=True)
    at_risk=summary[summary.shortage_intervals>0]
    if not at_risk.empty:
        st.warning(f'{at_risk.iloc[0].zone_name} has the largest total unmet demand in this scenario. First predicted shortage: {at_risk.iloc[0].first_shortage_UTC}. Allocation recommendations also consider declared zone priorities.')
    else:
        st.success('Every area’s planning demand is covered in every forecast interval under this scenario.')
    # Offer the established feasible solution from the original budget separately;
    # do not reuse capacity consumed by a manual move or silently undo that move.
    recommended,transfers=allocate(before,data.connections,method,medium,high)
    with st.expander('Compare with the automatic allocation alternative'):
        st.caption('Alternative to the manual decision, using the original budget and declared capacities. This is not an additional transfer plan to apply on top of the manual move.')
        st.metric('Unmet demand under automatic alternative',f'{recommended.remaining_shortage_m3.sum():,.1f} m³')
        st.dataframe(transfers,hide_index=True)
    st.download_button('Download admin impact assessment',summary.to_csv(index=False).encode(),'admin_impact.csv','text/csv')
    st.download_button('Download proposed supply schedule',updated.to_csv(index=False).encode(),'proposed_supply.csv','text/csv')
    with st.expander('Inspect interval-by-interval manual allocation'):
        st.dataframe(moves,hide_index=True)
