from pathlib import Path
import io
import os
import time
import base64
import json
import zipfile
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
from smart_water.data import demo, ValidationError
from smart_water.forecast import train, predict, save, load, MODELS, weather_scenario
from smart_water.allocation import shortage_plan, allocate
from smart_water.live import LiveStore, LiveError, sync
from smart_water.regional import PUBLIC_SOURCES, fetch_report
from smart_water.uploads import import_csvs
from smart_water.map_view import render_shortage_map
from smart_water.ui import apply_theme, sidebar_brand, context_bar
from smart_water.dashboard import render_dashboard

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='Smart Water Redistribution',page_icon='💧',layout='wide')
apply_theme()


def landing_context():
    """Read the location selected in the React landing page, if present."""
    location=str(st.query_params.get('location','')).strip()
    workspace=str(st.query_params.get('workspace','')).strip()
    source=str(st.query_params.get('source','')).strip()
    allowed={'Overview','Live dashboard','Demand forecast','Anomaly alerts','Shortage map','Shortage prediction','Redistribution','Data & methodology'}
    sources={'Public regional reports','Live connection','Upload CSVs','Demo CSV bundle','Synthetic demo'}
    if workspace in allowed:
        st.session_state.workspace_page=workspace
    if source in sources:
        st.session_state.data_source=source
    if not location:
        return None
    try:
        latitude=float(st.query_params.get('latitude',''))
        longitude=float(st.query_params.get('longitude',''))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
    except (TypeError,ValueError):
        latitude=longitude=None
    return {'name':location,'latitude':latitude,'longitude':longitude,'timezone':str(st.query_params.get('timezone','')).strip()}


selected_operating_location=landing_context()


@st.cache_data
def demo_data():
    return demo(seed=42)


def csv_download(label,frame,name,key=None):
    st.download_button(label,frame.to_csv(index=False).encode(),name,'text/csv',key=key)


def example_zip(data):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,frame in [('consumption',data.history),('supply',data.supply),('zones',data.zones),('connections',data.connections),('weather',data.weather)]:
            archive.writestr(f'{name}.csv',frame.to_csv(index=False))
    return output.getvalue()


def draw_map(zones,summary,transfers):
    if 'latitude' not in zones:
        st.info('Add latitude and longitude to zone metadata to enable the map.')
        return
    mapped=zones.merge(summary,on='zone_id')
    mapped['color']=mapped.remaining_shortage_m3.map(lambda v:[230,109,71,210] if v>0.01 else [8,126,139,220])
    lookup=zones.set_index('zone_id')
    paths=[]
    if not transfers.empty:
        for (source,destination),g in transfers.groupby(['source_zone','destination_zone']):
            paths.append({'start':[float(lookup.loc[source,'longitude']),float(lookup.loc[source,'latitude'])],
                          'end':[float(lookup.loc[destination,'longitude']),float(lookup.loc[destination,'latitude'])],
                          'volume_m3':float(g.volume_m3.sum())})
    layers=[pdk.Layer('ScatterplotLayer',mapped,get_position='[longitude, latitude]',get_fill_color='color',
                      get_radius=400,pickable=True),
            pdk.Layer('TextLayer',mapped,get_position='[longitude, latitude]',get_text='zone_id',get_size=16,
                      get_color=[255,255,255],get_text_anchor='middle',get_alignment_baseline='center')]
    if paths:
        layers.insert(0,pdk.Layer('ArcLayer',paths,get_source_position='start',get_target_position='end',
                                 get_source_color=[8,126,139,150],get_target_color=[230,109,71,180],get_width=4))
    style={'version':8,'sources':{},'layers':[{'id':'background','type':'background','paint':{'background-color':'#f1f0ff'}}]}
    style_url='data:application/json;base64,'+base64.b64encode(json.dumps(style).encode()).decode()
    st.pydeck_chart(pdk.Deck(layers=layers,map_style=style_url,initial_view_state=pdk.ViewState(
        latitude=float(zones.latitude.mean()),longitude=float(zones.longitude.mean()),zoom=11,pitch=15),
        tooltip={'text':'{zone_name}\nLatest observed interval: {current_demand_m3} m³\nForecast total: {predicted_demand} m³\nPeak shortage risk: {peak_risk}\nRemaining shortage: {remaining_shortage_m3} m³'}))
    st.caption('Coordinate map • teal: demand met after transfers · orange: remaining shortage. '
               'Arcs show direct recommended transfers. No external basemap or map API key required.')


with st.sidebar:
    sidebar_brand()
    with st.expander('Data source',expanded=False):
        source=st.radio('Data source',['Public regional reports','Live connection','Upload CSVs','Demo CSV bundle','Synthetic demo'],key='data_source')
    page=st.radio('Workspace',['Overview','Live dashboard','Demand forecast','Anomaly alerts','Shortage map','Shortage prediction','Redistribution','Data & methodology'],disabled=source=='Public regional reports',key='workspace_page')
    st.divider()

if source=='Public regional reports':
    st.caption('SMART WATER REDISTRIBUTION / MUMBAI METROPOLITAN REGION')
    st.title('Regional water reports')
    st.write('Mumbai, Thane, Kalyan–Dombivli and nearby areas. Public reports are fetched automatically; no files to upload.')
    city=st.selectbox('City',list(PUBLIC_SOURCES))
    @st.cache_data(ttl=900,show_spinner=False)
    def public_report(city):
        try:
            return fetch_report(city),None
        except LiveError as exc:
            return None,str(exc)
    @st.fragment(run_every='60s')
    def regional_panel():
        if st.button('Check for an updated report'):
            public_report.clear()
        with st.spinner('Checking the public report…'):
            report,error=public_report(city)
        if error:
            st.error(error)
        else:
            st.caption('Observation date: '+str(pd.Timestamp(report['reported_at']).date())+
                       ' · Retrieved: '+pd.Timestamp(report['fetched_at']).tz_convert('Asia/Kolkata').strftime('%d %b %Y, %H:%M IST'))
            if report['stale']:
                st.warning('OLD OBSERVATION — the source is reachable, but its latest published reading is more than two days old. This is not a real-time measurement.')
            else:
                st.info('Dated public reservoir report. This is not live household or ward consumption.')
            a,b,c=st.columns(3)
            a.metric('Reported reservoir storage',f"{report['stored_ml']:,.0f} ML")
            b.metric('Reported capacity',f"{report['capacity_ml']:,.0f} ML")
            c.metric('Reported fullness',f"{report['percent_full']:.2f}%")
            plot=pd.DataFrame({'Volume':['Stored','Unfilled capacity'],
                'ML':[report['stored_ml'],max(0,report['capacity_ml']-report['stored_ml'])]})
            st.plotly_chart(px.bar(plot,x='ML',y='Volume',orientation='h',color='Volume',
                                  color_discrete_sequence=['#00649a','#dedff2']),use_container_width=True)
            st.caption(report['provenance'])
            st.link_button('View original public report',report['source_url'])
        st.caption('Checks while this page is open; public report fetches are cached for 15 minutes. A new fetch does not imply a new observation.')
    regional_panel()
    st.warning('Neighbourhood demand forecasting and redistribution are unavailable for these public reports: timestamped consumption, interval supply and network capacities have not been verified.')
    st.markdown('Reservoir stock is a volume held in storage. It cannot be substituted for daily city consumption or a fresh supply allocation in every forecast hour. '
                'Do not add city totals together: cities may share reservoirs, and reported storage accounting can differ.')
    with st.expander('Verified source availability and next connection'):
        st.markdown('- **Mumbai:** BMC reports / community republication provide reservoir storage, not ward consumption.\n'
                    '- **Thane:** the public report is dated reservoir storage; a live municipal consumption API is not verified.\n'
                    '- **Kalyan–Dombivli:** the indexed official GIS schema lists pumping stations; the direct query returned an HTML configuration page during verification, not usable measurement JSON.\n'
                    '- **Real demand forecasts:** connect an authorized utility or meter API using **Live connection**. The automatic ingestion, forecasting and monitoring workflow is ready for that feed.')
        st.link_button('BMC hydraulic department','https://crmapp.mcgm.gov.in/irj/portal/anonymous/qlhydrlc')
        st.link_button('KDMC public GIS schema','https://maps.kdmc.gov.in/agserver/rest/services/KDMC_BASEMAP_24_04_2025/MapServer/104')
    st.stop()

def choose_forecast():
    st.session_state.workspace_page='Demand forecast'

def choose_csv():
    st.session_state.data_source='Upload CSVs'
    st.session_state.workspace_page='Demand forecast'

live_status=None
live_store=None
train_requested=False
if source=='Live connection':
    with st.sidebar.expander('Data connection',expanded=True):
        endpoint=st.text_input('Water-data API URL',value=os.environ.get('WATER_API_URL',''),
            help='A utility or meter gateway endpoint using the live JSON contract. Configure private API tokens on the server.')
        auto_refresh=st.checkbox('Refresh automatically every minute',value=True)
        auto_train=st.checkbox('Train automatically when observations change',value=True)
        refresh=st.button('Refresh now')
    if not endpoint:
        st.caption('CITY WATER PLANNING / LIVE CONNECTION')
        st.title('Connect the city’s water data')
        st.write('Live observations → updated demand forecasts → shortage alerts → redistribution recommendations')
        st.warning('No real data source is connected yet. Forecasts will appear after a verified utility or meter feed is connected.')
        st.markdown('A public source must provide actual consumption over time for the relevant city. '
                    'Rainfall, river levels and reservoir storage alone do not measure neighbourhood demand. '
                    'We also need a supply schedule and declared connections to recommend redistribution.')
        st.button('Upload CSV & generate forecasts',type='primary',on_click=choose_csv)
        st.info('Use a CSV to forecast immediately from historical readings, or configure an API for automatic updates.')
        st.caption('A city-specific public-data adapter is pending source discovery. The connection accepts the documented JSON contract; it cannot interpret an arbitrary website URL.')
        with st.expander('Automatic connection setup'):
            st.code('WATER_API_URL=https://your-provider.example/water/snapshot\nWATER_API_TOKEN=<optional server-side token>',language='text')
            st.write('Integration details: docs/LIVE_DATA.md. Never enter credentials into the URL.')
        st.markdown('**Live features unlock as data arrives:** consumption history + zone metadata enables forecasts and monitoring; historical weather enables weather impact comparisons; future supply enables shortage analysis; connection capacities enable redistribution; zone coordinates enable the network map.')
        st.stop()
    @st.fragment(run_every='60s' if auto_refresh else None)
    def refresh_clock():
        if time.monotonic()-st.session_state.get('live_refresh_clock',0)>55:
            st.session_state.live_refresh_clock=time.monotonic()
            st.rerun()
    st.session_state.live_refresh_clock=time.monotonic()
    refresh_clock()
    live_store=LiveStore(Path(os.environ.get('SMART_WATER_LIVE_STORE', ROOT/'artifacts'/'live.sqlite3')))
    last_fetch=st.session_state.get('last_live_fetch',0)
    if refresh or endpoint!=st.session_state.get('live_endpoint') or time.monotonic()-last_fetch>50:
        try:
            with st.spinner('Reading the latest provider snapshot…'):
                st.session_state.live_result=sync(endpoint,live_store,os.environ.get('WATER_API_TOKEN','') if endpoint==os.environ.get('WATER_API_URL') else '')
            st.session_state.live_error=None
        except LiveError as exc:
            st.session_state.live_result=None
            st.session_state.live_error=str(exc)
        st.session_state.live_endpoint=endpoint
        st.session_state.last_live_fetch=time.monotonic()
    if st.session_state.get('live_result') is None:
        st.title('Live connection unavailable')
        st.error(st.session_state.get('live_error','No data received.'))
        st.info('No simulated readings have been substituted. Check the source or wait for the next automatic retry.')
        st.stop()
    data,live_status=st.session_state.live_result
    if live_status['stale']:
        st.warning('STALE DATA — showing the last validated snapshot. Live operational recommendations are paused.')
        if live_status['error']:
            st.error(live_status['error'])
    else:
        st.success('Connected to '+live_status['source_name'])
    st.caption(f"Last successful fetch: {live_status['fetched_at']} · Latest completed observation: {live_status['latest_observation']} · All times UTC")
elif source=='Upload CSVs':
    st.caption('CITY WATER PLANNING / CSV FORECASTING')
    st.title('Upload data & forecast demand')
    st.write('Start with consumption history. Add supply and connections for shortage analysis and redistribution.')
    with st.expander('Required columns, parameters and example files',expanded=True):
        st.markdown('**Consumption:** `timestamp, zone_id, consumption_m3`. Optional `temperature, rainfall` columns are supported. '
                    'Volumes are m³ per interval; temperature is °C and rainfall is mm. '
                    'Hourly history needs at least 35 days; daily history needs at least 70 observations per zone.')
        st.markdown('**Forecast parameters:** model, horizon, historical lags and calendar patterns, plus weather when supplied. '
                    '**Planning parameters:** supply availability, zone priorities, transfer capacities, conservative upper-band demand and risk thresholds. '
                    'Supply and priorities affect planning; they do not change the learned demand forecast.')
        st.download_button('Download complete example CSV bundle',example_zip(demo_data()),'synthetic_examples.zip','application/zip')
        sample=demo_data()
        csv_download('Download consumption + weather example (synthetic)',sample.history.merge(sample.weather,on='timestamp'),'consumption_with_weather.csv')
    history_file=st.file_uploader('Consumption history CSV (required)',type='csv',key='csv_history')
    left,right=st.columns(2)
    with left:
        frequency=st.selectbox('Observation interval',['Hourly','Daily'],key='csv_frequency')
    with right:
        cumulative=st.checkbox('Cumulative meter readings (meter_m3)',key='csv_cumulative')
    with st.expander('Optional supply, zone, connection and weather files'):
        st.caption('Supply: timestamp, zone_id, available_supply_m3. Zones: zone_id, zone_name, priority_weight (optional latitude/longitude). '
                   'Connections: source_zone, destination_zone, capacity_m3 (optional transfer_cost). Weather: timestamp, temperature, rainfall.')
        supply_file=st.file_uploader('Future supply CSV',type='csv',key='csv_supply')
        zones_file=st.file_uploader('Zone metadata CSV',type='csv',key='csv_zones')
        connections_file=st.file_uploader('Transfer connections CSV',type='csv',key='csv_connections')
        weather_file=st.file_uploader('Historical weather CSV',type='csv',key='csv_weather')
    st.caption('Timestamps use UTC; include an offset for local times. Missing readings are not zero. '
               'Cumulative resets require reconciliation. Daily data stays daily.')
    if history_file is None:
        st.info('Upload consumption history, then select Generate forecasts. No live API connection is needed.')
        st.stop()
    try:
        content=lambda upload: upload.getvalue() if upload is not None else None
        data=import_csvs(content(history_file),content(supply_file),content(zones_file),content(connections_file),
                         content(weather_file),'h' if frequency=='Hourly' else 'D',cumulative)
    except ValidationError as exc:
        st.error(str(exc));st.stop()
    if zones_file is None:
        st.caption('Zone names use the supplied IDs; priority weights default to 1 (equal priority). No coordinates are invented.')
    if data.supply.empty:
        st.info('Forecast-only mode: supply is not provided, so shortages and transfers cannot be calculated.')
    elif data.connections.empty:
        st.info('No transfer connections supplied. Shortages can be calculated, but no transfers will be assumed.')
    st.success(f'Validated {len(data.history):,} observations across {len(data.zones)} zones.')
    with st.expander('Preview uploaded consumption'):
        st.dataframe(data.history.head(100),hide_index=True)
    train_requested=st.button('Generate forecasts',type='primary',on_click=choose_forecast)
    auto_train=False
elif source=='Demo CSV bundle':
    folder=ROOT/'outputs'/'demo_csv_bundle'
    try:
        read=lambda name:(folder/(name+'.csv')).read_bytes()
        data=import_csvs(read('consumption_with_weather'),read('supply'),read('zones'),read('connections'))
    except (OSError,ValidationError) as exc:
        st.error(f'Demo CSV bundle unavailable: {exc}'); st.stop()
    data.synthetic=True
    auto_train=False
    st.caption('Loaded the prepared demo CSV files. These are synthetic readings, not a live municipal feed.')
else:
    data=demo_data()
    auto_train=False

# Reuse matching artifacts; live observations can explicitly opt into automatic training.
key=data.fingerprint
if st.session_state.get('bundle_key') != key:
    st.session_state.bundle=load(data,ROOT/'artifacts')
    st.session_state.bundle_key=key
with st.sidebar.expander('Model training',expanded=False):
    retrain=st.button('Retrain & evaluate models',use_container_width=True)
if retrain or train_requested or (st.session_state.bundle is None and (data.synthetic or (auto_train and not live_status['stale']))):
    with st.spinner('Training and evaluating at past forecast origins. This runs once; models are then saved.'):
        st.session_state.bundle=train(data)
        save(st.session_state.bundle,ROOT/'artifacts')
bundle=st.session_state.bundle
if bundle is None:
    st.info('Data is ready. Select “Generate forecasts” above.' if source=='Upload CSVs' else 'Data is ready. Select “Retrain & evaluate models” to fit and save the forecasting models.')
    st.stop()

with st.sidebar:
    with st.expander('Forecast & planning',expanded=page=='Live dashboard'):
        model=st.selectbox('Forecast model',MODELS)
        maximum=bundle['metadata']['evaluation_horizon']
        unit='hours' if data.frequency=='h' else 'days'
        options=[x for x in ([24,48,72] if data.frequency=='h' else [1,3,7]) if x<=maximum]
        if not options:
            options=[maximum]
        horizon=st.selectbox(f'Forecast horizon ({unit})',options)
        conservative=st.toggle('Conservative demand',help='Plan against the upper empirical demand band instead of the point forecast.')
        method=st.selectbox('Allocation method',['Optimization','Priority baseline'])
        with st.expander('Scenario & risk settings',expanded=page=='Live dashboard'):
            supply_pct=st.slider('Scheduled supply available (%)',0,150,100,5)
            temperature_shift=st.slider('Temperature scenario shift (°C)',-10.,10.,0.,.5,disabled=data.weather.empty or model=='Seasonal naive')
            rainfall_shift=st.slider('Rainfall scenario shift (mm/interval)',-5.,10.,0.,.5,disabled=data.weather.empty or model=='Seasonal naive')
            medium=st.number_input('Medium risk starts at (%)',min_value=0.1,max_value=99.,value=10.)
            high=st.number_input('High risk starts at (%)',min_value=0.2,max_value=100.,value=25.)
        st.caption(f'Model saved • {bundle["metadata"]["trained_at"][:10]}\n\nAll chart times: UTC')
st.markdown('<div class="workspace-eyebrow">Operations / '+page+'</div>',unsafe_allow_html=True)
page_titles={'Live dashboard':'All areas, updating with your decisions','Overview':'Water operations, at a glance','Demand forecast':'Understand tomorrow’s demand','Anomaly alerts':'Keep unusual usage in sight','Shortage map':'A clearer view of every zone','Shortage prediction':'See shortages before they happen','Redistribution':'Put available water where it’s needed','Data & methodology':'The data behind each decision'}
st.title(page_titles[page])
st.caption('Smart Water Redistribution · Forecast demand. Review risk. Plan the response.')
context_items=[source,f'{len(data.zones)} zones',f'{horizon} {unit} forecast',model,'All times UTC']
if selected_operating_location:
    context_items.insert(1,f'Operating context: {selected_operating_location["name"]}')
context_bar(context_items)
if selected_operating_location:
    coordinates='' if selected_operating_location['latitude'] is None else f" · {selected_operating_location['latitude']:.4f}, {selected_operating_location['longitude']:.4f}"
    st.info('Operating location received from the landing page: '+selected_operating_location['name']+coordinates+'. This selects the planning context; the loaded dataset remains the source of all forecasts and measurements.')

if data.synthetic:
    st.info('Demo scenario · Mumbai-region city names with synthetic water readings and assumed connections. Results do not represent measured city performance.')
else:
    st.info('Planning scenario using declared connections. Capacity constraints are checked; hydraulic feasibility is not validated.')

forecast=predict(bundle,data,horizon,model,temperature_shift,rainfall_shift)
supply=data.supply.copy()
supply['available_supply_m3']*=supply_pct/100
planning_error=None
try:
    plan=shortage_plan(forecast,supply,data.zones,conservative,medium,high)
    result,transfers=allocate(plan,data.connections,method,medium,high)
except ValidationError as exc:
    planning_error='Provide a future supply schedule through the API or CSV upload to enable shortage analysis. Demand forecasts remain available.' if data.supply.empty else str(exc)
    result=transfers=None
alerts=bundle['alerts'].query('model == @model')
if live_status is not None:
    if not live_status['stale']:
        # Only the unmodified weather scenario is monitored, so scenario experiments cannot create alerts.
        monitoring_forecast=predict(bundle,data,horizon,model)
        live_store.record_forecasts(live_status['key'],monitoring_forecast,bundle,model)
    monitored=live_store.monitored(live_status['key'],data.history,model)
    alerts=monitored[monitored.severity!='Normal'] if not monitored.empty else monitored
    if live_status['stale']:
        planning_error='Live recommendations paused because observations are stale or the provider is unavailable. Historical forecasts remain available for analysis.'
alert_period='live monitored observations' if live_status is not None else 'evaluated test windows' 
if live_status is not None:
    with st.expander('Live feature availability',expanded=True):
        st.caption('The same models, scenario controls and exports used in the demo operate on this provider’s validated readings.')
        st.dataframe(pd.DataFrame([
            {'Feature':'Demand forecast & model evaluation','Availability':'Available — observed consumption history'},
            {'Feature':'Weather impact comparison','Availability':('Available — select Random forest or Extra trees and adjust weather scenarios' if not data.weather.empty else 'Needs historical temperature and rainfall')},
            {'Feature':'Shortages & supply scenarios','Availability':planning_error or 'Available for the selected horizon'},
            {'Feature':'Redistribution & optimization','Availability':planning_error or ('Needs declared transfer connections' if data.connections.empty else 'Available — uses declared capacities and priorities')},
            {'Feature':'Network map','Availability':planning_error or ('Available' if 'latitude' in data.zones else 'Needs zone latitude and longitude')},
            {'Feature':'Live anomaly alerts','Availability':('Paused — stale observations' if live_status['stale'] else ('Monitoring saved predictions against arriving actuals' if not monitored.empty else 'Collecting predictions — alerts start when actuals arrive'))},
        ]),hide_index=True,use_container_width=True)
        st.caption('Weather adjustments are model scenarios, not a live weather forecast. Stale data pauses operational recommendations. Forecast and evaluation CSV exports are in Demand forecast.')


if page=='Live dashboard':
    render_dashboard(data,bundle,forecast,result,transfers,planning_error,model,horizon,conservative,method,medium,high,live_status)
elif page=='Overview':
    st.subheader(f'Next {horizon} {unit} at a glance')
    if planning_error:
        st.info(planning_error)
        st.metric('Predicted demand',f'{forecast.predicted_demand.sum():,.0f} m³')
        st.plotly_chart(px.line(forecast,x='timestamp',y='predicted_demand',color='zone_id',labels={'predicted_demand':'Forecast (m³ per interval)'}),use_container_width=True)
        csv_download('Download future forecast',forecast,'forecast.csv')
        st.stop()
    cols=st.columns(4)
    cols[0].metric('Predicted demand',f'{forecast.predicted_demand.sum():,.0f} m³')
    cols[1].metric('Available supply',f'{result.available_supply_m3.sum():,.0f} m³')
    cols[2].metric('Shortage before transfers',f'{result.shortage_m3.sum():,.0f} m³')
    cols[3].metric('Shortage after transfers',f'{result.remaining_shortage_m3.sum():,.0f} m³')
    st.caption(f'{result.loc[result.shortage_m3>0,"zone_id"].nunique()} zones at risk before transfers · '
               f'{len(alerts)} anomaly alerts in {alert_period} · '
               f'{transfers.volume_m3.sum():,.0f} m³ recommended for transfer · '
               f'{"Upper-band" if conservative else "Point-forecast"} demand planning')
    summary=result.groupby('zone_id',as_index=False)[['predicted_demand','planned_demand','available_supply_m3','shortage_m3','remaining_shortage_m3']].sum()
    latest=data.history.sort_values('timestamp').groupby('zone_id').tail(1)[['zone_id','consumption_m3']].rename(columns={'consumption_m3':'current_demand_m3'})
    peak=result.sort_values('shortage_pct').groupby('zone_id').tail(1)[['zone_id','risk']].rename(columns={'risk':'peak_risk'})
    summary=summary.merge(latest,on='zone_id').merge(peak,on='zone_id')
    left,right=st.columns([1.15,1])
    with left:
        st.markdown('#### Distribution network')
        draw_map(data.zones,summary,transfers)
        st.caption(f'Latest observed interval: {data.history.timestamp.max()} · Forecast totals cover {horizon} {unit}; risk is the worst interval before transfers.')
    with right:
        st.markdown('#### Shortage by zone')
        plot=summary.merge(data.zones[['zone_id','zone_name']],on='zone_id')
        fig=px.bar(plot,x=['shortage_m3','remaining_shortage_m3'],y='zone_name',orientation='h',barmode='group',
                   color_discrete_sequence=['#e66d47','#00649a'],labels={'value':'Shortage (m³)','zone_name':'','variable':'Stage'})
        fig.for_each_trace(lambda t:t.update(name={'shortage_m3':'Before','remaining_shortage_m3':'After'}[t.name]))
        fig.update_layout(height=370,legend_title_text='',margin=dict(l=0,r=0,t=10,b=0))
        st.plotly_chart(fig,use_container_width=True)
    st.markdown('#### Interval balance')
    balance=result.groupby('timestamp',as_index=False)[['planned_demand','available_supply_m3','supply_after_m3']].sum()
    st.plotly_chart(px.line(balance,x='timestamp',y=['planned_demand','available_supply_m3'],
        color_discrete_sequence=['#004f87','#00649a'],labels={'value':'m³ per interval','timestamp':'Time (UTC)','variable':'Measure'}),use_container_width=True)
    st.caption('Redistribution changes where water is available, not total supply. Residual shortages may remain because of insufficient supply or connection capacity.')

elif page=='Demand forecast':
    st.subheader('Demand forecast')
    zone=st.selectbox('Zone',data.zones.zone_id,format_func=lambda z:data.zones.set_index('zone_id').loc[z,'zone_name'])
    past=data.history.query('zone_id == @zone').tail(7*24 if data.frequency=='h' else 28)
    future=forecast.query('zone_id == @zone')
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=past.timestamp,y=past.consumption_m3,name='Observed',line=dict(color='#004f87')))
    fig.add_trace(go.Scatter(x=future.timestamp,y=future.upper_m3,name='90% nominal band',line=dict(width=0),showlegend=True))
    fig.add_trace(go.Scatter(x=future.timestamp,y=future.lower_m3,fill='tonexty',fillcolor='rgba(0,165,155,0.16)',line=dict(width=0),showlegend=False))
    fig.add_trace(go.Scatter(x=future.timestamp,y=future.predicted_demand,name=model,line=dict(color='#00649a',width=3)))
    fig.update_layout(yaxis_title='Consumption (m³ per interval)',xaxis_title='Time (UTC)',height=440,legend=dict(orientation='h'))
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Band width is the per-zone 90th percentile absolute validation residual, pooled across evaluated forecast leads. '
               'Test coverage below is empirical, not a guarantee. Drift and changed weather scenarios can invalidate calibration. '
               'Future weather uses a past-only hour-of-day climatology scenario with the selected shifts; no observed future weather is used.')
    st.markdown('#### Compare with the same intervals last week')
    comparison_history=future[['timestamp','predicted_demand']].copy()
    comparison_history['historical_timestamp']=comparison_history.timestamp-pd.Timedelta(days=7)
    comparison_history=comparison_history.merge(data.history.query('zone_id == @zone')[['timestamp','consumption_m3']].rename(columns={'timestamp':'historical_timestamp','consumption_m3':'last_week_consumption_m3'}),on='historical_timestamp',how='left')
    st.caption(f'Selected future period: {future.timestamp.min()} to {future.timestamp.max()} UTC. Change Forecast horizon in the sidebar to compare 24, 48 or 72 hours for hourly data.')
    st.plotly_chart(px.line(comparison_history,x='timestamp',y=['predicted_demand','last_week_consumption_m3'],labels={'value':'Volume (m³ per interval)','timestamp':'Forecast time (UTC)','variable':'Series'}),use_container_width=True)
    csv_download('Download historical comparison',comparison_history,'historical_comparison.csv')
    st.markdown('#### How weather changes predicted demand')
    if data.weather.empty:
        st.info('Provide historical temperature and rainfall through the API weather array or CSV upload to learn weather effects. No weather effect is invented from consumption alone.')
    elif model=='Seasonal naive':
        st.info('Seasonal naive repeats last week’s demand and does not use weather. Choose Random forest or Extra trees to compare weather scenarios.')
    else:
        baseline=predict(bundle,data,horizon,model)
        reference=baseline.query('zone_id == @zone')
        comparison=future[['timestamp','zone_id','predicted_demand']].rename(columns={'predicted_demand':'adjusted_weather_demand_m3'}).merge(
            reference[['timestamp','zone_id','predicted_demand']].rename(columns={'predicted_demand':'baseline_weather_demand_m3'}),on=['timestamp','zone_id'])
        comparison['weather_change_m3']=comparison.adjusted_weather_demand_m3-comparison.baseline_weather_demand_m3
        origin=data.history.timestamp.max()
        weather=data.weather.set_index('timestamp')
        dates=pd.DatetimeIndex(comparison.timestamp)
        base_weather=weather_scenario(weather,dates,origin)
        adjusted_weather=weather_scenario(weather,dates,origin,temperature_shift,rainfall_shift)
        comparison['baseline_temperature_c']=base_weather[:,0]
        comparison['adjusted_temperature_c']=adjusted_weather[:,0]
        comparison['baseline_rainfall_mm']=base_weather[:,1]
        comparison['adjusted_rainfall_mm']=adjusted_weather[:,1]
        before=comparison.baseline_weather_demand_m3.sum()
        after=comparison.adjusted_weather_demand_m3.sum()
        change=after-before
        a,b,c=st.columns(3)
        a.metric('Baseline weather demand',f'{before:,.1f} m³')
        b.metric('Adjusted weather demand',f'{after:,.1f} m³')
        c.metric('Weather scenario effect',f'{change:+,.1f} m³',delta=f'{100*change/before:+.2f}%' if before>0 else 'Baseline demand is zero',delta_color='off')
        st.caption(f'Selected zone · next {horizon} {unit} · temperature shift {temperature_shift:+g} °C · rainfall shift {rainfall_shift:+g} mm/interval. '
                   'Change the weather sliders in Scenario & risk settings to update this comparison.')
        st.plotly_chart(px.line(comparison,x='timestamp',y=['baseline_weather_demand_m3','adjusted_weather_demand_m3'],
            labels={'value':'Predicted demand (m³ per interval)','timestamp':'Time (UTC)','variable':'Weather scenario'},
            color_discrete_sequence=['#004f87','#e66d47']),use_container_width=True)
        st.caption('Both forecasts use the same history, model and horizon; only future weather changes. '
                   'The baseline uses recent observed hour-of-day averages. Adjustments are scenarios, not a live meteorological forecast. '
                   'Differences are model associations, not a proven causal effect. Tree models may show no response to small changes or outside the training range; '
                   'uncertainty bands have not been separately calibrated for changed weather.')
        with st.expander('Weather inputs and demand effect for every forecast interval'):
            st.dataframe(comparison,hide_index=True,use_container_width=True)
        csv_download('Download weather impact comparison',comparison,'weather_impact.csv')
    st.markdown('#### Model comparison')
    st.dataframe(bundle['metrics'],hide_index=True,use_container_width=True,column_config={'band_coverage':st.column_config.NumberColumn('Band coverage (fraction)',format='%.3f')})
    st.caption('ALL is the pooled zone-interval metric. Both models use the same rolling origins and horizons. Validation calibrates bands; Test measures held-out performance. No fixed accuracy claim.')
    with st.expander('Inspect forecasts made at historical origins'):
        st.dataframe(bundle['evaluation'].query('zone_id == @zone and model == @model'),hide_index=True)
    csv_download('Download future forecast',forecast,'forecast.csv')
    csv_download('Download evaluation metrics',bundle['metrics'],'metrics.csv')

elif page=='Shortage map':
    if planning_error:
        st.info(planning_error); st.stop()
    render_shortage_map(data,result,transfers)

elif page=='Shortage prediction':
    st.subheader('Shortage prediction')
    if planning_error:
        st.info(planning_error); st.stop()
    st.write('Compare predicted demand with scheduled supply for each zone and forecast interval.')
    summary=plan.groupby(['zone_id','zone_name'],as_index=False).agg(
        predicted_demand_m3=('predicted_demand','sum'),planned_demand_m3=('planned_demand','sum'),
        available_supply_m3=('available_supply_m3','sum'),estimated_shortage_m3=('shortage_m3','sum'),
        peak_shortage_pct=('shortage_pct','max'),intervals_at_risk=('shortage_m3',lambda values:int((values>0).sum())))
    summary=summary.sort_values(['peak_shortage_pct','estimated_shortage_m3'],ascending=False)
    a,b,c=st.columns(3)
    a.metric('Zones facing shortage',int((summary.estimated_shortage_m3>0).sum()))
    b.metric('Expected shortage',f'{summary.estimated_shortage_m3.sum():,.1f} m³')
    c.metric('Intervals with shortage',int((plan.groupby('timestamp').shortage_m3.sum()>0).sum()))
    st.caption('Shortages are summed per interval: a surplus at another time does not cancel a shortage. Conservative mode uses upper-band planned demand. Peak shortage percentage is a severity measure, not a probability.')
    st.dataframe(summary,hide_index=True,use_container_width=True)
    st.plotly_chart(px.bar(summary,x='zone_name',y=['predicted_demand_m3','available_supply_m3','estimated_shortage_m3'],
        barmode='group',labels={'value':'Volume (m³)','zone_name':'Zone','variable':'Measure'},
        color_discrete_sequence=['#004f87','#00649a','#e66d47']),use_container_width=True)
    st.markdown('#### Risk by zone and interval')
    st.plotly_chart(px.scatter(plan,x='timestamp',y='zone_name',color='risk',size='shortage_m3',
        color_discrete_map={'None':'#dedff2','Low':'#e9b949','Medium':'#e66d47','High':'#ba2525'},
        hover_data=['predicted_demand','planned_demand','available_supply_m3','shortage_m3','shortage_pct']),use_container_width=True)
    st.dataframe(plan[['timestamp','zone_name','predicted_demand','planned_demand','available_supply_m3','shortage_m3','shortage_pct','risk']],hide_index=True)
    csv_download('Download shortage predictions',plan,'shortage_predictions.csv')

elif page=='Anomaly alerts':
    st.subheader('Abnormal consumption detection')
    st.write('Alerts compare observed consumption with forecasts issued before those observations. Both high and low deviations are retained.')
    st.caption(('Live monitoring: only predictions saved before the observation interval ended are scored. ' if live_status is not None else 'Historical monitoring replay: three evaluated test windows, not continuous live monitoring. ')+
               'Per-zone threshold = 99th percentile absolute validation residual. Medium exceeds this threshold; High exceeds twice it. '
               'Possible leakage, unusual activity, interruptions or sensor issues require investigation.')
    st.metric('Alerts in '+alert_period,len(alerts))
    if alerts.empty:
        st.success('No monitored anomalies yet. Live scoring starts after a saved forecast receives its actual observation.' if live_status is not None else 'No residuals exceeded the calibrated thresholds in these windows.')
    else:
        latest=alerts.sort_values('timestamp').groupby('zone_id',as_index=False).tail(1).merge(data.zones[['zone_id','zone_name']],on='zone_id')
        st.markdown('#### Most recent detected deviation in each affected zone')
        st.caption('These are dated detected events; an older alert does not establish that a zone is currently abnormal.')
        for row in latest.itertuples():
            message=f'{row.zone_name} · {row.severity} · {row.timestamp}: observed {row.actual:,.1f} m³ vs expected {row.expected:,.1f} m³ ({row.residual:+,.1f} m³).'
            (st.error if row.severity=='High' else st.warning)(message)
        st.plotly_chart(px.scatter(alerts,x='timestamp',y='residual',color='zone_id',symbol='severity',
            hover_data=['actual','expected','threshold_m3'],labels={'residual':'Actual − expected (m³)','timestamp':'Time (UTC)'}),use_container_width=True)
        st.dataframe(alerts[['zone_id','timestamp','origin','actual','expected','residual','threshold_m3','severity','explanation']],hide_index=True,use_container_width=True)
    csv_download('Download alert details',alerts,'anomaly_alerts.csv')

elif page=='Redistribution':
    st.subheader('Redistribution plan')
    if planning_error:
        st.error(planning_error); st.stop()
    st.write('Direct donor-to-recipient transfers only. Every donor retains its planned demand; every transfer respects declared capacity.')
    a,b=st.columns(2)
    a.metric('Water redistributed',f'{transfers.volume_m3.sum():,.1f} m³')
    b.metric('Remaining unmet demand',f'{result.remaining_shortage_m3.sum():,.1f} m³')
    st.caption(f'Risk: low >0–<{medium:g}%, medium {medium:g}–<{high:g}%, high ≥{high:g}%. These are configurable categories, not probabilities.')
    if transfers.empty:
        st.info('No feasible direct transfers under this scenario. Check donor surplus, recipient need and allowed connections.')
    else:
        st.markdown('#### Recommended transfers and reasons')
        st.dataframe(transfers,hide_index=True,use_container_width=True)
    st.markdown('#### Before and after, by interval')
    st.dataframe(result[['timestamp','zone_name','predicted_demand','planned_demand','available_supply_m3','shortage_m3','shortage_pct','risk','sent_m3','received_m3','remaining_shortage_m3','risk_after']],hide_index=True,use_container_width=True)
    st.caption('Optimization first minimizes unmet demand weighted by zone priority, shortage risk and relative predicted demand, then minimizes transfer cost while preserving the first optimum. '
               'The baseline orders recipients by the same demand-and-risk priority score. No multi-hop routing, storage carryover, pipe loss or pressure simulation is assumed.')
    csv_download('Download transfer recommendations',transfers,'transfers.csv')
    csv_download('Download interval balance',result,'water_balance.csv')

else:
    st.subheader('Data & methodology')
    st.download_button('Download synthetic example CSVs',example_zip(demo_data()),'synthetic_examples.zip','application/zip')
    st.markdown('''**Data contract.** Consumption, supply and capacities are cubic metres per declared interval. Weather is °C and mm per interval. All inputs use a common UTC grid. Zeros are measurements; gaps are unknown and rejected. Supply schedules are deliveries available each interval, not reservoir stock. CSV units cannot be inferred from numeric values: convert at the source.

**Forecasting.** A seasonal-naive model repeats last week's matching interval. A pooled Random Forest uses one-hot zone identity, hour cycles, weekday/weekend, month/season, lag 1, previous day/week, and strictly past rolling means and variability. Weather is used when supplied. No holiday calendar is inferred. Recursive forecasts use their own preceding predictions.

**Evaluation.** History is split chronologically 60/20/20. Three non-overlapping origins in each validation/test segment generate multi-step forecasts. The model is frozen within each segment, fit on training data for validation and on training plus validation for test. Each origin can use observations already received. Final deployment model is refit on all history; test scores describe earlier fitted models, not future performance.

**Uncertainty and anomalies.** Validation residuals calibrate zone-specific bands and high/low anomaly thresholds. Coverage is measured separately on test data. Bands pool forecast leads and do not promise simultaneous coverage across zones or intervals. Anomalies remain in the data; there is no silent outlier removal. Explicit retraining adapts the model to new history.

**Redistribution.** Linear programming enforces donor surplus, recipient need, declared direct connections and per-interval capacity. A second optimization minimizes cost at the best priority-weighted allocation. WNTR is not required or integrated; hydraulic feasibility needs a separately calibrated physical network model.

**Reference review.** See `docs/REFERENCES.md` for inspected source files, licenses and the Kaggle access limitation. This project's implementation is original; reference code and datasets are not bundled.''')
    st.json(bundle['metadata'])
    for title,frame in [('Consumption history',data.history),('Supply schedule',data.supply),('Zone metadata',data.zones),('Transfer connections',data.connections),('Historical weather',data.weather)]:
        with st.expander(title):
            st.dataframe(frame.head(1000),hide_index=True,use_container_width=True)
            csv_download('Download '+title.lower(),frame,title.lower().replace(' ','_')+'.csv')
