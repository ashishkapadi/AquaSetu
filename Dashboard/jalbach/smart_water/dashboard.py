"""All-zone interactive scenario comparison without invented live observations."""
import pandas as pd
import plotly.express as px
import streamlit as st
from .forecast import predict
from .allocation import shortage_plan, allocate
from .data import ValidationError
from .admin import render_admin


def demand_comparison(forecast, baseline, zones):
    comparison=forecast.merge(baseline[['timestamp','zone_id','predicted_demand']].rename(
        columns={'predicted_demand':'baseline_demand_m3'}),on=['timestamp','zone_id'],validate='one_to_one')
    comparison['demand_change_m3']=comparison.predicted_demand-comparison.baseline_demand_m3
    return comparison.merge(zones[['zone_id','zone_name']],on='zone_id',validate='many_to_one')


def render_dashboard(data,bundle,forecast,result,transfers,planning_error,model,horizon,conservative,method,medium,high,live_status):
    view=st.radio('Dashboard view',['All-area predictions','Admin allocation'],horizontal=True)
    if view=='Admin allocation':
        st.caption(f'Latest observation: {data.history.timestamp.max()} · Forecast: {forecast.timestamp.min()} to {forecast.timestamp.max()} UTC')
        st.caption('Live-feed observations refresh according to the API refresh setting. Demo and CSV inputs remain fixed snapshots; scenario changes recalculate on each committed control change.')
        render_admin(data,forecast,result,planning_error,conservative,method,medium,high)
        return
    st.subheader('Every area. Every parameter change.')
    st.write('Use Forecast & planning in the sidebar. Results recalculate when you release a slider or change a selection—no training button is needed for scenario changes.')
    stamp=pd.Timestamp.now(tz='UTC').strftime('%H:%M:%S UTC')
    st.caption(f'Calculated: {stamp} · Latest observation: {data.history.timestamp.max()} · Forecast: {forecast.timestamp.min()} to {forecast.timestamp.max()}')
    if live_status:
        st.caption(f"Provider last fetched: {live_status['fetched_at']} · {'Stale snapshot; operational planning paused' if live_status['stale'] else 'API updates follow the automatic refresh setting (every minute while open)'}")
    else:
        st.caption('Interactive scenario dashboard · This dataset is a fixed snapshot, not a live sensor stream. Calculation time is not observation time.')
    st.caption('Comparison baseline: original scheduled supply (100%), no temperature/rainfall shifts. Model, horizon, risk thresholds and conservative-demand setting match your current selection. Deltas are against this baseline, not the previous click.')
    baseline=predict(bundle,data,horizon,model)
    comparison=demand_comparison(forecast,baseline,data.zones)
    summary=comparison.groupby(['zone_id','zone_name'],as_index=False)[['predicted_demand','baseline_demand_m3','demand_change_m3']].sum()
    cols=st.columns(min(3,len(summary)))
    for i,row in enumerate(summary.itertuples()):
        cols[i%len(cols)].metric(row.zone_name,f'{row.predicted_demand:,.1f} m³',delta=f'{row.demand_change_m3:+,.1f} m³ vs baseline',delta_color='off')
    st.caption('Cards show total predicted consumption across the selected horizon. Supply adjustments change shortages and transfers, not predicted consumption. Weather changes may produce zero model response, especially with Seasonal naive.')
    curves=comparison.melt(id_vars=['timestamp','zone_name'],value_vars=['predicted_demand','baseline_demand_m3'],var_name='Scenario',value_name='Demand (m³/interval)')
    curves['Scenario']=curves.Scenario.map({'predicted_demand':'Current scenario','baseline_demand_m3':'Baseline'})
    fig=px.line(curves,x='timestamp',y='Demand (m³/interval)',color='Scenario',facet_col='zone_name',facet_col_wrap=2,
        color_discrete_map={'Current scenario':'#00649a','Baseline':'#98a2b3'},height=max(400,260*((len(summary)+1)//2)))
    fig.for_each_annotation(lambda a:a.update(text=a.text.split('=')[-1]))
    st.plotly_chart(fig,use_container_width=True)
    st.markdown('#### Area balances & changes')
    if planning_error:
        st.info(planning_error)
    else:
        try:
            base_result,_=allocate(shortage_plan(baseline,data.supply,data.zones,conservative,medium,high),data.connections,method,medium,high)
            fields=['available_supply_m3','shortage_m3','remaining_shortage_m3','received_m3','sent_m3']
            totals=result.groupby('zone_id',as_index=False)[fields].sum()
            base_totals=base_result.groupby('zone_id',as_index=False)[fields].sum()
            summary=summary.merge(totals,on='zone_id').merge(base_totals.rename(columns={c:'baseline_'+c for c in fields}),on='zone_id')
            for col in ['available_supply_m3','shortage_m3','remaining_shortage_m3']:
                summary['change_'+col]=summary[col]-summary['baseline_'+col]
            worst=result.sort_values('remaining_shortage_pct').groupby('zone_id').tail(1)[['zone_id','risk_after']]
            summary=summary.merge(worst,on='zone_id')
            a,b,c=st.columns(3)
            a.metric('Available supply',f'{result.available_supply_m3.sum():,.1f} m³',delta=f'{summary.change_available_supply_m3.sum():+,.1f} m³ vs baseline',delta_color='off')
            b.metric('Shortage before transfers',f'{result.shortage_m3.sum():,.1f} m³',delta=f'{summary.change_shortage_m3.sum():+,.1f} m³ vs baseline',delta_color='inverse')
            c.metric('Shortage after transfers',f'{result.remaining_shortage_m3.sum():,.1f} m³',delta=f'{summary.change_remaining_shortage_m3.sum():+,.1f} m³ vs baseline',delta_color='inverse')
            st.caption('Shortages sum interval deficits. Risk is the worst remaining interval risk. Negative shortage changes mean improvement; positive changes mean additional unmet demand.')
            with st.expander('Current recommended transfers'):
                st.dataframe(transfers,hide_index=True)
        except ValidationError as exc:
            st.info(f'Baseline supply comparison unavailable: {exc}')
    st.dataframe(summary,hide_index=True,use_container_width=True)
    st.download_button('Download all-area scenario comparison',summary.to_csv(index=False).encode(),'all_area_comparison.csv','text/csv')
    st.download_button('Download all-area interval predictions',comparison.to_csv(index=False).encode(),'all_area_predictions.csv','text/csv')
