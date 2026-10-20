"""Interactive shortage map shared by demo, uploaded and connected datasets."""
import json
import pandas as pd
import pydeck as pdk
import streamlit as st
from .data import ValidationError
from .risk_map import area_summary, demo_boundaries, parse_boundaries, feature_collection


def render_shortage_map(data,result,transfers):
    st.subheader('Shortage alerts & redistribution map')
    st.write('Find where planned demand exceeds supply, then compare the proposed redistribution.')
    if 'latitude' not in data.zones:
        st.info('Add latitude and longitude to the zone metadata to locate zones on the map.')
        return
    period=st.selectbox('Map forecast period',['Entire selected horizon']+list(result.timestamp.drop_duplicates().sort_values()),
        format_func=lambda value:value if isinstance(value,str) else str(value)+' UTC')
    after=st.radio('Map shows',['Before redistribution','After redistribution'],horizontal=True)=='After redistribution'
    show_transfers=st.checkbox('Show recommended transfer routes',value=True)
    basemap=st.checkbox('Show street basemap',value=True,help='Uses the online CARTO / OpenStreetMap basemap. Turn off if map tiles are unavailable.')
    selected=result if isinstance(period,str) else result[result.timestamp==period]
    routes=transfers if isinstance(period,str) else transfers[transfers.timestamp==period]
    summary=area_summary(selected,data.history,data.zones)
    geometries=None
    with st.expander('Area boundaries'):
        st.caption('Optional GeoJSON: FeatureCollection, one Polygon or MultiPolygon per zone, properties.zone_id matching the CSV, WGS84 longitude/latitude. Uploaded boundaries replace illustrative areas.')
        uploaded=st.file_uploader('Zone boundaries GeoJSON',type=['geojson','json'])
        if uploaded is not None:
            try:
                if uploaded.size>5*1024*1024:
                    raise ValidationError('Boundary file must be at most 5 MB.')
                geometries=parse_boundaries(json.loads(uploaded.getvalue()),set(data.zones.zone_id))
            except (ValueError,UnicodeError) as exc:
                st.error(str(exc)); return
    if geometries is None and data.synthetic:
        geometries=demo_boundaries(data.zones)
        st.info('Mumbai-region city labels and approximate map locations are used for this demo. Outlines, water readings and connections are illustrative—not verified municipal boundaries or infrastructure.')
    elif geometries is None:
        st.info('Showing measured zone locations only. Upload actual service-area boundaries for the outlined area map; boundaries are not inferred from coordinates.')
    st.caption(f'Period: {selected.timestamp.min()} to {selected.timestamp.max()} UTC · Latest observed interval: {data.history.timestamp.max()} UTC. Volumes are summed over the selected period; risk is the worst interval. Surpluses at other times do not erase shortages.')
    st.markdown('🟢 No shortage · 🟡 Low · 🟠 Medium · 🔴 High · Blue lines: proposed direct transfers')
    layers=[]
    if geometries:
        features=feature_collection(summary,geometries,after)
        layers += [pdk.Layer('GeoJsonLayer',features,id='area-halos',filled=False,stroked=True,
            get_line_color='properties.fill',get_line_width=12,line_width_min_pixels=12,line_width_units='pixels'),
            pdk.Layer('GeoJsonLayer',features,id='risk-areas',filled=True,stroked=True,pickable=True,
                get_fill_color='properties.fill',get_line_color='properties.color',get_line_width=3,line_width_min_pixels=3,line_width_units='pixels')]
    points=feature_collection(summary,{z:None for z in summary.zone_id},after)['features']
    point_data=[f['properties'] for f in points]
    layers.append(pdk.Layer('ScatterplotLayer',point_data,id='zone-markers',get_position='[longitude, latitude]',
        get_fill_color='color',get_radius=110,pickable=True))
    layers.append(pdk.Layer('TextLayer',point_data,id='zone-labels',get_position='[longitude, latitude]',
        get_text='zone_name',get_size=13,get_color=[35,48,62],get_pixel_offset=[0,-22],background=True,
        get_background_color=[255,255,255,210]))
    lookup=data.zones.set_index('zone_id')
    if show_transfers and not routes.empty:
        paths=[{'start':[lookup.loc[a,'longitude'],lookup.loc[a,'latitude']],
                'end':[lookup.loc[b,'longitude'],lookup.loc[b,'latitude']]} for a,b in routes.groupby(['source_zone','destination_zone']).groups]
        layers.append(pdk.Layer('ArcLayer',paths,id='recommended-transfers',get_source_position='start',get_target_position='end',
            get_source_color=[30,100,190,170],get_target_color=[30,100,190,230],get_width=3))
    view=pdk.data_utils.compute_view(data.zones[['longitude','latitude']].to_numpy())
    view.pitch=0
    view.zoom=min(view.zoom,11)
    st.pydeck_chart(pdk.Deck(layers=layers,map_style='light' if basemap else None,map_provider='carto' if basemap else None,
        initial_view_state=view,height=580,tooltip={'text':
        '{zone_name}\nRisk: {display_risk}\nLatest observed: {latest_observed_m3} m³/interval\nPredicted demand: {predicted_demand} m³\nPlanning demand: {planned_demand} m³\nAvailable supply: {available_supply_m3} m³\nShortage before: {shortage_m3} m³\nReceive: {received_m3} m³ | Send: {sent_m3} m³\nRemaining shortage: {remaining_shortage_m3} m³'}),use_container_width=True,key='shortage_area_map_v3')
    st.markdown('#### Zone alert & proposed response')
    zone=st.selectbox('Inspect zone',summary.zone_id,format_func=lambda z:lookup.loc[z,'zone_name'])
    row=summary.set_index('zone_id').loc[zone]
    a,b,c=st.columns(3)
    a.metric('Predicted demand',f'{row.predicted_demand:,.1f} m³')
    b.metric('Available supply',f'{row.available_supply_m3:,.1f} m³')
    c.metric('Shortage after transfers' if after else 'Shortage before transfers',f'{row.remaining_shortage_m3 if after else row.shortage_m3:,.1f} m³')
    if row.shortage_m3>0:
        st.warning(f'{row.zone_name}: demand exceeds scheduled supply in at least one selected interval. Peak risk before transfers: {row.risk_before}. This may cause insufficient service if no corrective action is taken; the forecast does not establish a physical cause.')
        incoming=routes[routes.destination_zone==zone]
        if not incoming.empty:
            st.write('Proposed solution: receive water over the declared direct connections below, while donors retain their planning demand.')
            st.dataframe(incoming[['timestamp','source_zone','destination_zone','volume_m3','reason']],hide_index=True)
        else:
            st.info('No feasible incoming transfer is available under the declared supply and connection capacities.')
        if row.remaining_shortage_m3>1e-6:
            st.error(f'{row.remaining_shortage_m3:,.1f} m³ remains unmet. Review additional authorized supply or demand reduction; the current network cannot fully cover this scenario.')
        else:
            st.success('The proposed transfers cover the estimated shortage for this selected period.')
    else:
        st.success('Scheduled supply covers planning demand in each selected interval.')
        st.write(f'Proposed outgoing transfers: {row.sent_m3:,.1f} m³.')
    st.caption('Change Scheduled supply available (%) and weather scenarios in the sidebar to recalculate the map and recommendations. Proposed routes are planning recommendations, not verified hydraulic paths. Conservative mode compares upper-band planning demand against supply.')
    st.download_button('Download mapped zone balances',summary.to_csv(index=False).encode(),'mapped_zone_balances.csv','text/csv')
