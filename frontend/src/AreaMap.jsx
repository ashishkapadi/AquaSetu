import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, CircleHelp, LoaderCircle, Pause, Play, RotateCcw, Waves } from 'lucide-react';
import './AreaMap.css';

const fmt = (value, digits = 1) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
const mapName = (value, index) => {
  const match = String(value || '').match(/^DMA[\s_-]*(\d+)\b/i);
  return match ? `DMA ${match[1]}` : `Area ${index + 1}`;
};
function apiError(body, status) {
  const detail = Array.isArray(body?.detail) ? body.detail.map(x => x.msg || x.message || '').filter(Boolean).join('; ') : body?.detail;
  return detail || body?.message || `Request failed (${status})`;
}
function timestamp(value, timezone = 'UTC') {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  try { return date.toLocaleString(undefined, { timeZone: timezone, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }); }
  catch { return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); }
}

function layoutFor(count) {
  const columns = count <= 12 ? Math.min(3, count) : Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / columns);
  const width = 860, height = 500, marginX = 25, marginY = 24;
  const cellW = (width - marginX * 2) / columns, cellH = (height - marginY * 2) / rows;
  const signed = n => (Math.abs(n * 9301 + 49297) % 233280) / 116640 - 1;
  const node = (c, r) => ({ x: marginX + c * cellW + (c > 0 && c < columns ? signed(c * 19 + r * 3) * 8 : 0), y: marginY + r * cellH + (r > 0 && r < rows ? signed(r * 31 + c * 7) * 8 : 0) });
  const horizontal = (c, r) => { const a = node(c, r), b = node(c + 1, r); return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 + signed(c * 23 + r * 11 + 5) * 9 }; };
  const vertical = (c, r) => { const a = node(c, r), b = node(c, r + 1); return { x: (a.x + b.x) / 2 + signed(c * 13 + r * 29 + 9) * 9, y: (a.y + b.y) / 2 }; };
  return Array.from({ length: count }, (_, index) => {
    const c = index % columns, r = Math.floor(index / columns);
    const points = [node(c, r), horizontal(c, r), node(c + 1, r), vertical(c + 1, r), node(c + 1, r + 1), horizontal(c, r + 1), node(c, r + 1), vertical(c, r)];
    const center = { x: points.reduce((sum, p) => sum + p.x, 0) / points.length, y: points.reduce((sum, p) => sum + p.y, 0) / points.length };
    return { points: points.map(p => `${p.x},${p.y}`).join(' '), center };
  });
}

function coverageClass(zone, allocation, busy) {
  if (!allocation || busy) return 'pending';
  const item = allocation.zones?.find(x => x.id === zone.id);
  if (Number(item?.demand) === 0) return 'no-demand';
  const coverage = Number(item?.coverage_pct);
  if (!Number.isFinite(coverage)) return 'pending';
  return coverage >= 95 ? 'covered' : coverage >= 75 ? 'watch' : 'shortage';
}

export default function AreaMap({ dashboard, allocation, supply, onSupplyChange, priorities, onPriorityChange, horizon, busy = false, error = '' }) {
  const zones = dashboard?.zones || [];
  const unit = dashboard?.source?.unit || allocation?.unit || 'dataset units';
  const timezone = dashboard?.source?.timezone || 'UTC';
  const [selectedId, setSelectedId] = useState(zones[0]?.id || '');
  const [playback, setPlayback] = useState(false);
  const [frames, setFrames] = useState([]);
  const [frameIndex, setFrameIndex] = useState(0);
  const [loadingFrames, setLoadingFrames] = useState(false);
  const [timelineError, setTimelineError] = useState('');
  const [timelineNote, setTimelineNote] = useState('');
  const [playing, setPlaying] = useState(false);
  const timelineRequest = useRef(0);
  const currentAlloc = playback ? frames[frameIndex]?.allocation || null : busy ? null : allocation;
  const allocationBusy = !playback && busy;
  const geometry = useMemo(() => layoutFor(zones.length), [zones.length]);
  const selected = zones.find(z => z.id === selectedId) || zones[0];
  const selectedAllocation = currentAlloc?.zones?.find(z => z.id === selected?.id);
  const supplyNumber = Number(supply);
  const dashboardDemand = zones.reduce((sum, zone) => sum + (Number(zone.predicted_demand) || 0), 0);
  const rangeMax = Math.max(1, Number(dashboard?.default_supply || 0) * 2, dashboardDemand * 2);

  useEffect(() => {
    if (!zones.some(z => z.id === selectedId)) setSelectedId(zones[0]?.id || '');
  }, [zones, selectedId]);

  useEffect(() => {
    if (!playback || supply === '' || !Number.isFinite(supplyNumber) || supplyNumber < 0) {
      timelineRequest.current++;
      setFrames([]); setFrameIndex(0); setLoadingFrames(false); setTimelineError(''); setTimelineNote(''); setPlaying(false);
      return undefined;
    }
    const controller = new AbortController();
    const requestId = ++timelineRequest.current;
    setFrames([]); setFrameIndex(0); setPlaying(false); setTimelineError(''); setTimelineNote(''); setLoadingFrames(true);
    const timer = setTimeout(async () => {
      try {
        const response = await fetch('/api/map-timeline', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hourly_supply: supplyNumber / Math.max(1, Number(horizon) || 1), priorities: priorities || {} }), signal: controller.signal });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(apiError(body, response.status));
        if (requestId === timelineRequest.current) {
          setFrames(Array.isArray(body.frames) ? body.frames : []);
          setTimelineNote(body.note || '');
          setTimelineError(body.frames?.length ? '' : 'The service returned no forecast hours.');
        }
      } catch (err) {
        if (!controller.signal.aborted && requestId === timelineRequest.current) setTimelineError(err.message || 'Could not load scenario playback.');
      } finally { if (requestId === timelineRequest.current) setLoadingFrames(false); }
    }, 350);
    return () => { clearTimeout(timer); controller.abort(); if (timelineRequest.current === requestId) timelineRequest.current++; };
  }, [playback, supply, supplyNumber, horizon, priorities, dashboard]);

  useEffect(() => {
    if (!playing || frames.length === 0) return undefined;
    const lastIndex = Math.min(23, frames.length - 1);
    const timer = setInterval(() => setFrameIndex(index => Math.min(lastIndex, index + 1)), 1000);
    return () => clearInterval(timer);
  }, [playing, frames.length]);
  useEffect(() => { if (playing && frames.length && frameIndex >= Math.min(23, frames.length - 1)) setPlaying(false); }, [playing, frames.length, frameIndex]);

  function selectZone(id) { setSelectedId(id); }
  function keySelect(event, id) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectZone(id); } }

  return <section className="area-map" aria-label="Illustrative district allocation map">
    <header className="area-map-head">
      <div><span className="area-map-kicker"><Waves size={14} /> DISTRICT COVERAGE</span><h2>Allocation by area</h2><p>Illustrative district boundaries · historical forecast, not live sensors{dashboard?.forecast_origin && <> · Last measured {timestamp(dashboard.forecast_origin, timezone)}</>}</p></div>
      <div className="area-map-legend" aria-label="Coverage colors"><span><i className="covered" /> ≥95% covered</span><span><i className="watch" /> 75–&lt;95%</span><span><i className="shortage" /> &lt;75%</span><span><i className="pending" /> Pending</span><span><i className="no-demand" /> No demand</span></div>
    </header>

    <div className="area-map-playback">
      <label className="area-map-toggle"><input type="checkbox" checked={playback} onChange={e => { setPlayback(e.target.checked); setFrameIndex(0); setPlaying(false); }} /><span>24-hour forecast playback</span></label>
      {playback && <div className="area-map-timeline">
        {loadingFrames ? <span className="area-map-loading"><LoaderCircle size={15} className="area-spin" /> Preparing 24-hour scenario…</span> : <>
          <button type="button" className="area-icon-button" disabled={!frames.length} onClick={() => { if (!playing && frameIndex === frames.length - 1) setFrameIndex(0); setPlaying(value => !value); }} aria-label={playing ? 'Pause playback' : 'Play forecast playback'}>{playing ? <Pause size={15} /> : <Play size={15} />}</button>
          <button type="button" className="area-icon-button" disabled={!frames.length} onClick={() => { setPlaying(false); setFrameIndex(0); }} aria-label="Reset playback"><RotateCcw size={14} /></button>
          <label className="area-hour-slider"><span>Hour {frames.length ? frameIndex + 1 : '—'} / 24</span><input type="range" min="0" max={Math.max(0, Math.min(23, frames.length - 1))} value={Math.min(frameIndex, Math.max(0, frames.length - 1))} disabled={!frames.length} onChange={e => { setPlaying(false); setFrameIndex(Number(e.target.value)); }} aria-label="Select playback hour" /></label>
          {frames[frameIndex]?.timestamp && <span className="area-frame-time">{timestamp(frames[frameIndex].timestamp, timezone)}</span>}
        </>}
      </div>}
      {playback && !loadingFrames && <p className="area-playback-note">Scenario playback redistributes uniform hourly supply ({fmt(supplyNumber / Math.max(1, Number(horizon) || 1))} {unit} per forecast hour) against a frozen historical forecast. It is a planning simulation, not live sensor replay.{timelineNote && <> {timelineNote}</>}</p>}
    </div>

    {(error || timelineError) && <div className="area-map-error"><AlertCircle size={16} />{timelineError || error}</div>}

    <div className="area-map-layout">
      <div className="area-map-canvas">
        {zones.length > 0 ? <svg viewBox="0 0 860 500" role="group" aria-label="Schematic district coverage areas" className="area-map-svg">
          <defs><pattern id="area-map-dots" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#dbe7e1" /></pattern></defs>
          <rect x="0" y="0" width="860" height="500" fill="url(#area-map-dots)" />
          {zones.map((zone, index) => {
            const shape = geometry[index]; const item = currentAlloc?.zones?.find(x => x.id === zone.id);
            const color = coverageClass(zone, currentAlloc, allocationBusy);
            const active = selected?.id === zone.id;
            const coverage = Number(item?.coverage_pct);
            const noDemand = Number(item?.demand) === 0;
            const label = mapName(zone.name, index);
            return <g key={zone.id} className={`area-map-zone ${color} ${zones.length > 12 ? 'dense' : ''} ${active ? 'active' : ''}`} role="button" tabIndex={0} aria-pressed={active} aria-label={`${zone.name}; ${noDemand ? 'no forecast demand' : Number.isFinite(coverage) ? `${fmt(coverage, 0)} percent covered` : 'allocation pending'}`} onClick={() => selectZone(zone.id)} onKeyDown={event => keySelect(event, zone.id)}>
              <polygon points={shape.points} />
              <text className="area-zone-name" x={shape.center.x} y={shape.center.y - 8}>{label}</text>
              <text className="area-zone-value" x={shape.center.x} y={shape.center.y + 15}>{noDemand ? 'No demand' : Number.isFinite(coverage) ? `${fmt(coverage, 0)}%` : 'Pending'}</text>
              <title>{zone.name}{noDemand ? ' · no forecast demand' : Number.isFinite(coverage) ? ` · ${fmt(coverage, 1)}% covered` : ' · allocation pending'}</title>
            </g>;
          })}
        </svg> : <div className="area-map-empty"><CircleHelp size={20} /> District areas appear after a model is ready.</div>}
      </div>

      <aside className="area-detail" aria-live="polite">
        {selected ? <>
          <div className="area-detail-head"><span className={`area-status-chip ${coverageClass(selected, currentAlloc, allocationBusy)}`}>{coverageClass(selected, currentAlloc, allocationBusy) === 'pending' ? 'Allocation pending' : coverageClass(selected, currentAlloc, allocationBusy) === 'no-demand' ? 'No forecast demand' : `${fmt(selectedAllocation?.coverage_pct, 0)}% covered`}</span><span className="area-index">{String(zones.indexOf(selected) + 1).padStart(2, '0')} / {String(zones.length).padStart(2, '0')}</span></div>
          <h3>{selected.name}</h3>
          {playback && frames[frameIndex]?.timestamp && <p className="area-detail-time">Forecast hour · {timestamp(frames[frameIndex].timestamp, timezone)}</p>}
          <div className="area-facts"><div><span>Latest measured hourly volume · {timestamp(dashboard?.forecast_origin, timezone)}</span><b>{fmt(selected.current_consumption, 2)} {unit}</b></div><div><span>{playback ? 'Forecast-hour demand' : `Predicted demand · ${horizon}h`}</span><b>{playback && !selectedAllocation ? 'Scenario pending' : Number(selectedAllocation?.demand ?? (!playback ? selected.predicted_demand : undefined)) === 0 ? 'No demand' : selectedAllocation ? `${fmt(selectedAllocation.demand, 2)} ${unit}` : !playback ? `${fmt(selected.predicted_demand, 2)} ${unit}` : '—'}</b></div><div><span>Allocated</span><b>{selectedAllocation ? `${fmt(selectedAllocation.allocation, 2)} ${unit}` : 'Scenario pending'}</b></div><div><span>Uncovered demand</span><b className={(Number(selectedAllocation?.shortage) || 0) > 0 ? 'area-shortage-value' : ''}>{selectedAllocation ? Number(selectedAllocation.demand) === 0 ? 'No demand' : `${fmt(selectedAllocation.shortage, 2)} ${unit}` : 'Scenario pending'}</b></div><div className="area-priority-row"><span>Priority weight</span><select aria-label={`Priority for ${selected.name}`} value={priorities?.[selected.id] ?? selected.priority ?? 3} onChange={e => onPriorityChange?.(selected.id, Number(e.target.value))}>{[1,2,3,4,5].map(value => <option key={value} value={value}>{value} · {value === 1 ? 'Lower' : value === 5 ? 'Higher' : 'Priority'}</option>)}</select></div></div>
        </> : <p className="area-map-empty">Select a district to inspect its scenario.</p>}
      </aside>
    </div>

    <div className="area-map-controls"><div><span className="area-map-kicker">ADJUSTABLE PLANNING SCENARIO</span><b>Available supply · {unit}</b><small>For the selected {horizon}-hour forecast window</small></div><div className="area-supply-inputs"><input type="number" min="0" step="any" value={supply ?? ''} onChange={event => onSupplyChange?.(event.target.value)} aria-label={`Available supply in ${unit}`} /><input type="range" min="0" max={rangeMax} step="any" value={Math.min(Math.max(0, supplyNumber || 0), rangeMax)} onChange={event => onSupplyChange?.(event.target.value)} aria-label="Adjust available supply" /></div></div>
    <footer className="area-map-foot"><span>Coverage colors show allocation share, not probabilities. Unused water is not carried between hours.</span>{currentAlloc && <span>Scenario supply: {fmt(currentAlloc.supply, 2)} {unit} · total shortage: {fmt(currentAlloc.shortage, 2)} {unit}</span>}</footer>
  </section>;
}
