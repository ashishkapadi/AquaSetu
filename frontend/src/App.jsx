import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, AlertCircle, ArrowDownRight, ArrowUpRight, Check, ChevronDown,
  CircleHelp, CloudUpload, Droplets, ExternalLink, FileText, Gauge, LayoutDashboard,
  LoaderCircle, MapPinned, RefreshCw, ShieldCheck, SlidersHorizontal, Waves, Zap,
} from 'lucide-react';
import {
  Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

const API = '/api';
const HORIZONS = [1, 6, 12, 24];

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map(item => item.msg || item.message || JSON.stringify(item)).join('; ')
      : body.detail || body.message;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return body;
}

function fmt(value, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}
function shortDate(value, withTime = false, timezone) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, withTime
    ? { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', ...(timezone === 'UTC' ? { timeZone: 'UTC' } : {}) }
    : { month: 'short', day: 'numeric', ...(timezone === 'UTC' ? { timeZone: 'UTC' } : {}) });
}
function fullDate(value, withTime = false, timezone) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, withTime
    ? { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', ...(timezone === 'UTC' ? { timeZone: 'UTC', timeZoneName: 'short' } : {}) }
    : { year: 'numeric', month: 'short', day: 'numeric', ...(timezone === 'UTC' ? { timeZone: 'UTC' } : {}) });
}
function errorText(error) { return error?.message || 'Something went wrong. Please try again.'; }

function IconButton({ children, onClick, disabled, title }) {
  return <button className="icon-button" type="button" onClick={onClick} disabled={disabled} title={title}>{children}</button>;
}

function Sidebar({ active, setActive, ready }) {
  const links = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'allocation', label: 'Allocation planner', icon: SlidersHorizontal },
    { id: 'zones', label: 'Zone priorities', icon: MapPinned },
    { id: 'evidence', label: 'Model evidence', icon: ShieldCheck },
  ];
  return <aside className="sidebar">
    <a className="brand" href="#overview" onClick={() => setActive('overview')}>
      <span className="brand-mark"><Droplets size={21} strokeWidth={2.2} /></span>
      <span><strong>requiem</strong><small>WATER INTELLIGENCE</small></span>
    </a>
    <div className="side-label">WORKSPACE</div>
    <nav className="side-nav" aria-label="Dashboard sections">
      {links.map(({ id, label, icon: Icon }) => <a key={id} href={`#${id}`} className={active === id ? 'selected' : ''} onClick={() => setActive(id)}>
        <Icon size={17} /><span>{label}</span>{id === 'allocation' && ready && <span className="nav-dot" />}
      </a>)}
    </nav>
    <div className="sidebar-spacer" />
    <div className="sidebar-status">
      <span className={`status-orb ${ready ? 'is-ready' : ''}`} />
      <div><strong>{ready ? 'Model ready' : 'Awaiting dataset'}</strong><span>{ready ? 'Forecast service active' : 'Upload a CSV to begin'}</span></div>
    </div>
    <a className="side-help" href="#setup" onClick={() => { if (ready) document.getElementById('setup')?.setAttribute('open', ''); }}><CircleHelp size={16} /> Data & setup</a>
    <div className="sidebar-foot">LOCAL OPERATIONS CONSOLE <span>v1.0</span></div>
  </aside>;
}

function MetricCard({ label, value, suffix, note, icon: Icon, tone = 'teal' }) {
  return <article className="metric-card">
    <div className={`metric-icon ${tone}`}><Icon size={17} /></div>
    <div className="metric-label">{label}</div>
    <div className="metric-value">{value}<span>{suffix}</span></div>
    <div className="metric-note">{note}</div>
  </article>;
}

function DemandChart({ data, unit, timezone }) {
  const firstForecast = data.findIndex(d => d.predicted !== undefined);
  return <div className="chart-wrap">
    <div className="chart-legend"><span><i className="legend-dot actual" /> Observed demand</span><span><i className="legend-dot forecast" /> Forecast</span></div>
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 14, right: 14, left: 0, bottom: 0 }}>
        <defs><linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#38a999" stopOpacity={0.2} /><stop offset="100%" stopColor="#38a999" stopOpacity={0.01} /></linearGradient></defs>
        <CartesianGrid vertical={false} stroke="#edf0ed" strokeDasharray="3 5" />
        <XAxis dataKey="timestamp" tickFormatter={v => shortDate(v, false, timezone)} tickLine={false} axisLine={false} minTickGap={35} tick={{ fill: '#909a96', fontSize: 11 }} />
        <YAxis tickLine={false} axisLine={false} width={46} tick={{ fill: '#909a96', fontSize: 11 }} tickFormatter={v => fmt(v, 0)} />
        <Tooltip content={({ active: shown, payload, label }) => shown && payload?.length ? <div className="chart-tooltip"><b>{shortDate(label, true, timezone)}</b>{payload.filter(p => p.value != null).map(p => <div key={p.dataKey}><i className={`legend-dot ${p.dataKey === 'actual' ? 'actual' : 'forecast'}`} />{p.dataKey === 'actual' ? 'Observed' : 'Forecast'} <strong>{fmt(p.value)} {unit}</strong></div>)}</div> : null} />
        <Area type="monotone" dataKey="actual" stroke="#229783" strokeWidth={2.3} fill="url(#actualFill)" connectNulls={false} activeDot={{ r: 4, fill: '#229783', stroke: '#fff', strokeWidth: 2 }} />
        <Line type="monotone" dataKey="predicted" stroke="#ee9a58" strokeWidth={2.3} strokeDasharray="5 5" dot={{ r: 3, fill: '#ee9a58', stroke: '#fff', strokeWidth: 2 }} activeDot={{ r: 4, fill: '#ee9a58', stroke: '#fff', strokeWidth: 2 }} connectNulls={false} />
      </ComposedChart>
    </ResponsiveContainer>
    {firstForecast >= 0 && <span className="chart-origin" style={{ left: `${Math.min(95, Math.max(8, (firstForecast / Math.max(data.length - 1, 1)) * 100))}%` }}>FORECAST ORIGIN</span>}
  </div>;
}

export function Onboarding({ status, onRefresh, retrain = false }) {
  const [file, setFile] = useState('');
  const [columns, setColumns] = useState([]);
  const [upload, setUpload] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState('');
  const [timestamp, setTimestamp] = useState('');
  const [target, setTarget] = useState('');
  const [zone, setZone] = useState('');
  const [unit, setUnit] = useState('dataset units');
  const fileRef = useRef(null);
  const datasets = status?.files || [];
  const selectedDataset = datasets.find(item => item.name === file);
  const availableColumns = upload?.columns || selectedDataset?.columns || columns;
  useEffect(() => {
    setUnit(selectedDataset?.unit || upload?.unit || 'dataset units');
  }, [file, selectedDataset?.unit, upload?.unit]);
  useEffect(() => {
    if (datasets.length && !file) setFile(datasets[0].name);
  }, [datasets, file]);
  useEffect(() => {
    const timeChoice = availableColumns.find(c => /time|date|stamp|hour/i.test(c)) || '';
    const targetChoice = availableColumns.find(c => /demand|consumption|flow|volume|usage|load/i.test(c) && c !== timeChoice) || '';
    const zoneChoice = availableColumns.find(c => /zone|region|district|area|site/i.test(c)) || '';
    if (timeChoice && !timestamp) setTimestamp(timeChoice);
    if (targetChoice && !target) setTarget(targetChoice);
    if (zoneChoice && !zone) setZone(zoneChoice);
  }, [availableColumns, timestamp, target, zone]);

  async function handleFile(fileObject) {
    if (!fileObject) return;
    setError(''); setUpload(null); setUploading(true);
    try {
      const form = new FormData(); form.append('file', fileObject);
      const result = await request('/upload', { method: 'POST', body: form });
      setUpload(result); setFile(result.name); setColumns(result.columns || []);
      setTimestamp(''); setTarget(''); setZone('');
      await onRefresh();
    } catch (err) { setError(errorText(err)); }
    finally { setUploading(false); }
  }
  async function startTraining(event) {
    event.preventDefault(); setError(''); setTraining(true);
    try {
      await request('/train', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename: file, timestamp_column: timestamp, target_column: target, zone_column: zone || null, unit: unit.trim() || 'dataset units' }) });
      setTraining(false);
      await onRefresh();
    } catch (err) { setError(errorText(err)); setTraining(false); }
  }
  const isTraining = training || status?.training;
  return <div className={`onboarding-grid ${retrain ? 'retrain-onboarding' : ''}`} id={retrain ? undefined : 'setup'}>
    <div className="onboarding-main">
      <div className="eyebrow"><span className="eyebrow-line" /> {retrain ? 'DATA & MODEL' : 'GET STARTED'}</div>
      <h2>{retrain ? <>Update your<br />forecast model.</> : <>Bring your water data<br />into focus.</>}</h2>
      <p className="onboarding-copy">Requiem learns from historical demand to help you plan distribution. Upload a CSV with hourly readings, map the fields, and train a local forecasting model.</p>
      {status?.error && <div className="notice warning"><AlertCircle size={17} /><span>{status.error}</span></div>}
      {error && <div className="notice error"><AlertCircle size={17} /><span>{error}</span></div>}
      {status?.training && <div className="training-banner"><LoaderCircle size={17} className="spin" /><span><b>Training in progress</b> — this can take a little while. We’ll update this view automatically.</span></div>}
      <div className="step-list">
        <div className="step-row"><span className="step-no">01</span><div><b>Upload a historical CSV</b><small>Use an hourly dataset with at least 28 days per series.</small></div><Check size={16} className="step-check" /></div>
        <div className="step-row"><span className="step-no">02</span><div><b>Map timestamp and demand</b><small>Choose genuine timestamp and observed target columns.</small></div><span className="step-pending" /></div>
        <div className="step-row"><span className="step-no">03</span><div><b>Train and review evidence</b><small>We compare the model with a simple baseline on held-out data.</small></div><span className="step-pending" /></div>
      </div>
    </div>
    <section className="setup-card">
      <div className="setup-card-head"><div><span className="card-kicker">DATASET SETUP</span><h3>{retrain ? 'Import or retrain' : 'Connect a dataset'}</h3></div><span className="local-pill"><span /> LOCAL</span></div>
      <button className={`dropzone ${uploading ? 'busy' : ''}`} onClick={() => fileRef.current?.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); handleFile(e.dataTransfer.files?.[0]); }} type="button" disabled={uploading}>
        {uploading ? <LoaderCircle size={22} className="spin" /> : <CloudUpload size={23} />}
        <b>{uploading ? 'Reading CSV…' : upload?.name || 'Choose a CSV file'}</b><span>Drop a file here or <u>browse</u></span>
        <small>Comma separated values · .csv</small>
      </button>
      <input ref={fileRef} className="visually-hidden" type="file" accept=".csv,text/csv" onChange={e => handleFile(e.target.files?.[0])} />
      {datasets.length > 0 && <label className="field-label">Available dataset<select value={file} onChange={e => { setFile(e.target.value); setUpload(null); setTimestamp(''); setTarget(''); setZone(''); }}><option value="" disabled>Select a dataset</option>{datasets.map(d => <option key={d.name} value={d.name}>{d.name} · {fmt(d.rows_preview, 0)} preview rows</option>)}</select></label>}
      {(availableColumns.length > 0) && <form className="mapping-form" onSubmit={startTraining}>
        <div className="mapping-title"><span>MAP YOUR COLUMNS</span><span>{availableColumns.length} detected</span></div>
        <label className="field-label">Timestamp column<select required value={timestamp} onChange={e => setTimestamp(e.target.value)}><option value="" disabled>Choose a timestamp</option>{availableColumns.map(c => <option key={c}>{c}</option>)}</select></label>
        <label className="field-label">Demand / target column<select required value={target} onChange={e => setTarget(e.target.value)}><option value="" disabled>Choose observed demand</option>{availableColumns.filter(c => c !== timestamp).map(c => <option key={c}>{c}</option>)}</select></label>
        <div className="form-pair"><label className="field-label">Zone column <span>optional</span><select value={zone} onChange={e => setZone(e.target.value)}><option value="">One series / no zone field</option>{availableColumns.filter(c => c !== timestamp && c !== target).map(c => <option key={c}>{c}</option>)}</select></label><label className="field-label">Target units<input value={unit} onChange={e => setUnit(e.target.value)} placeholder="dataset units" /></label></div>
        <button className="primary-button full" type="submit" disabled={isTraining || !file || !timestamp || !target}>{isTraining ? <><LoaderCircle size={16} className="spin" /> Training model…</> : <>Train local model <ArrowUpRight size={16} /></>}</button>
        <p className="fine-print">Training uses held-out historical observations. It won’t invent missing dates or measurements.</p>
      </form>}
      {!availableColumns.length && <div className="empty-mapping"><FileText size={16} /> Column mapping appears after upload.</div>}
    </section>
  </div>;
}

function App() {
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState('');
  const [dashboard, setDashboard] = useState(null);
  const [dashLoading, setDashLoading] = useState(false);
  const [dashError, setDashError] = useState('');
  const [horizon, setHorizon] = useState(1);
  const [allocation, setAllocation] = useState(null);
  const [supply, setSupply] = useState('');
  const [priorities, setPriorities] = useState({});
  const [allocLoading, setAllocLoading] = useState(false);
  const [allocError, setAllocError] = useState('');
  const [active, setActive] = useState('overview');
  const allocationTimer = useRef(null);
  const dashboardRequestId = useRef(0);
  const allocationRequestId = useRef(0);
  const wasTraining = useRef(false);
  const ready = Boolean(status?.ready);

  const refreshStatus = useCallback(async () => {
    try { const result = await request('/status'); setStatus(result); setStatusError(''); return result; }
    catch (error) { setStatusError(errorText(error)); return null; }
  }, []);
  useEffect(() => { refreshStatus(); }, [refreshStatus]);
  useEffect(() => {
    if (!status?.training) return undefined;
    const timer = window.setInterval(refreshStatus, 2000);
    return () => window.clearInterval(timer);
  }, [status?.training, refreshStatus]);
  const loadDashboard = useCallback(async (selectedHorizon, quiet = false) => {
    const requestId = ++dashboardRequestId.current;
    allocationRequestId.current += 1;
    setAllocation(null);
    setAllocLoading(false);
    setAllocError('');
    if (!quiet) setDashLoading(true);
    setDashError('');
    try {
      const data = await request(`/dashboard?horizon=${selectedHorizon}`);
      if (requestId !== dashboardRequestId.current) return null;
      setDashboard(data);
      setSupply(current => current === '' ? String(data.default_supply ?? '') : current);
      setPriorities(current => {
        const validIds = new Set((data.zones || []).map(zone => zone.id));
        const next = Object.fromEntries(Object.entries(current).filter(([id]) => validIds.has(id)));
        for (const zone of data.zones || []) if (next[zone.id] == null) next[zone.id] = zone.priority || 3;
        return next;
      });
      return data;
    } catch (error) {
      if (requestId === dashboardRequestId.current) { setDashError(errorText(error)); setDashboard(null); setAllocation(null); }
      return null;
    }
    finally { if (!quiet && requestId === dashboardRequestId.current) setDashLoading(false); }
  }, []);
  useEffect(() => {
    if (ready) loadDashboard(horizon);
    else { dashboardRequestId.current += 1; allocationRequestId.current += 1; setDashboard(null); setAllocation(null); }
  }, [ready, horizon, loadDashboard]);

  useEffect(() => {
    if (status?.training) wasTraining.current = true;
    else if (wasTraining.current && ready) { wasTraining.current = false; loadDashboard(horizon); }
  }, [status?.training, ready, horizon, loadDashboard]);

  const loadAllocation = useCallback(async () => {
    const requestId = ++allocationRequestId.current;
    if (!dashboard || dashboard.horizon !== horizon || supply === '' || !Number.isFinite(Number(supply)) || Number(supply) < 0) {
      setAllocation(null); setAllocLoading(false);
      setAllocError(supply !== '' && Number(supply) < 0 ? 'Supply must be zero or greater.' : '');
      return;
    }
    setAllocLoading(true); setAllocError('');
    try {
      const result = await request('/allocate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ horizon, supply: Number(supply), priorities, demand_multipliers: {} }) });
      if (requestId !== allocationRequestId.current) return;
      setAllocation(result);
    } catch (error) { if (requestId === allocationRequestId.current) { setAllocation(null); setAllocError(errorText(error)); } }
    finally { if (requestId === allocationRequestId.current) setAllocLoading(false); }
  }, [dashboard, supply, horizon, priorities]);
  useEffect(() => {
    window.clearTimeout(allocationTimer.current);
    if (!dashboard || dashboard.horizon !== horizon || supply === '' || !Number.isFinite(Number(supply)) || Number(supply) < 0) {
      allocationRequestId.current += 1;
      setAllocation(null); setAllocLoading(false);
      setAllocError(supply !== '' && Number(supply) < 0 ? 'Supply must be zero or greater.' : '');
      return undefined;
    }
    allocationTimer.current = window.setTimeout(loadAllocation, 280);
    return () => { window.clearTimeout(allocationTimer.current); allocationRequestId.current += 1; };
  }, [loadAllocation, dashboard, supply, horizon]);

  const chartData = useMemo(() => {
    if (!dashboard) return [];
    const history = dashboard.history || [];
    const forecast = dashboard.forecast || [];
    const combined = history.map(item => ({ timestamp: item.timestamp, actual: item.actual }));
    forecast.forEach((item, index) => {
      const last = combined[combined.length - 1];
      if (index === 0 && last && new Date(item.timestamp).getTime() === new Date(last.timestamp).getTime()) return;
      combined.push({ timestamp: item.timestamp, predicted: item.predicted });
    });
    return combined;
  }, [dashboard]);
  const source = dashboard?.source;
  const metrics = dashboard?.metrics;
  const zones = allocation?.zones || [];
  const zoneRows = allocation?.zones || (dashboard?.zones || []).map(zone => ({ ...zone, demand: zone.predicted_demand }));
  const actualZoneCount = source?.observed_zones;
  const simulatedCount = source?.simulated_zones;

  return <div className="app-shell">
    <Sidebar active={active} setActive={setActive} ready={ready} />
    <main className="main-area" id="overview">
      <header className="topbar"><div className="breadcrumb">Water operations <span>/</span> <b>Overview</b></div><div className="topbar-right"><span className="local-chip"><span className="live-dot" /> LOCAL INSTANCE</span><span className="top-divider" /><span className="today-label">{new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span><div className="avatar">R</div></div></header>
      <div className="page-content">
        <section className="page-heading">
          <div><div className="eyebrow"><span className="eyebrow-line" /> OPERATIONS OVERVIEW</div><h1>Water, with foresight.</h1><p>Forecast demand. Plan fairer distribution.</p></div>
          {ready && <div className="heading-actions"><div className="horizon-control"><label htmlFor="horizon">FORECAST</label><select id="horizon" value={horizon} onChange={e => { dashboardRequestId.current += 1; allocationRequestId.current += 1; setAllocation(null); setAllocLoading(false); setAllocError(''); setDashboard(null); setSupply(''); setHorizon(Number(e.target.value)); }} aria-label="Forecast horizon; supply resets to its suggested scenario for each horizon">{HORIZONS.map(h => <option key={h} value={h}>{h} hour{h > 1 ? 's' : ''}</option>)}</select><ChevronDown size={14} /></div><IconButton onClick={() => { refreshStatus(); loadDashboard(horizon); }} title="Refresh dashboard"><RefreshCw size={16} /></IconButton></div>}
        </section>
        {!ready ? <>
          {statusError && <div className="notice error page-error"><AlertCircle size={17} /><span>Can’t reach the local API: {statusError}</span><button onClick={refreshStatus}>Retry</button></div>}
          <Onboarding status={status} onRefresh={refreshStatus} />
        </> : <>
          {dashError && <div className="notice error page-error"><AlertCircle size={17} /><span>{dashError}</span><button onClick={() => loadDashboard(horizon)}>Retry</button></div>}
          {dashLoading && !dashboard ? <div className="loading-card"><LoaderCircle size={20} className="spin" /> Loading forecast and operational data…</div> : dashboard && <>
              <div className="source-strip"><span className="source-icon"><Waves size={16} /></span><div className="source-info"><b>{source?.name || 'Dataset'}</b><span>{source?.frequency || 'Observed history'}{source?.timezone ? ` · ${source.timezone}` : ''} <i /> {fmt(source?.rows, 0)} rows <i /> {fullDate(source?.start, false, source?.timezone)} – {fullDate(source?.end, false, source?.timezone)}</span></div><div className="source-tags"><span className="source-tag">{fmt(actualZoneCount, 0)} observed zones</span>{Boolean(simulatedCount) && <span className="source-tag simulated">{fmt(dashboard.zones?.length, 0)} illustrative zones · simulated</span>}<span className="source-unit">Unit: {source?.unit || 'dataset units'}</span></div></div>
            <div className="metrics-grid">
              <MetricCard label="Forecast demand" value={fmt(dashboard.forecast?.reduce((sum, p) => sum + (Number(p.predicted) || 0), 0))} suffix={<small> {source?.unit || 'units'}</small>} note={`Next ${horizon} hour${horizon > 1 ? 's' : ''} · summed volume`} icon={Droplets} />
              <MetricCard label="Selected model MAE" value={fmt(metrics?.selected_mae, 2)} suffix={<small> {source?.unit || 'units'}</small>} note="Next-hour held-out evaluation" icon={Gauge} tone="navy" />
              <MetricCard label="Baseline MAE" value={fmt(metrics?.baseline_mae, 2)} suffix={<small> {source?.unit || 'units'}</small>} note="Same unseen observations" icon={Activity} tone="sand" />
              <MetricCard label="Model improvement" value={metrics?.improvement_pct == null ? '—' : `${fmt(metrics.improvement_pct, 1)}%`} suffix="" note={metrics?.improvement_pct >= 0 ? 'Against seasonal baseline' : 'Baseline performed better'} icon={metrics?.improvement_pct >= 0 ? ArrowDownRight : ArrowUpRight} tone={metrics?.improvement_pct >= 0 ? 'teal' : 'orange'} />
            </div>
            <section className="panel chart-panel">
              <div className="panel-heading"><div><span className="card-kicker">DEMAND SIGNAL</span><h2>Observed & forecast demand</h2><p>Last 72 observed hours and the next {horizon} forecast hour{horizon > 1 ? 's' : ''} · {source?.unit || 'dataset units'}</p></div><span className="forecast-badge"><span /> {horizon}H OUTLOOK</span></div>
              <div className="chart-container">{chartData.length > 0 ? <DemandChart data={chartData} unit={source?.unit || 'units'} timezone={source?.timezone} /> : <div className="empty-chart">No time-series readings were returned for this view.</div>}</div>
              <div className="chart-foot"><span>Forecast origin <b>{fullDate(dashboard.forecast_origin, true, source?.timezone)}</b></span><span className="replay-label"><Activity size={13} /> Historical replay · not live city telemetry</span></div>
            </section>
            <section className="anomaly-section" aria-labelledby="anomaly-title">
              <div className="section-heading section-heading-tight"><div><div className="eyebrow"><span className="eyebrow-line" /> LATEST OBSERVATION</div><h2 id="anomaly-title">Unusual consumption</h2><p>At {fullDate(dashboard.forecast_origin, true, source?.timezone)} · Observed current-hour use compared with the model’s expected level and alert threshold.{Boolean(simulatedCount) && ' Alerts are inherited from the measured series across illustrative zones.'}</p></div><span className="alert-count">{(dashboard.zones || []).filter(zone => zone.anomaly).length} flagged</span></div>
              <div className="panel anomaly-panel"><div className="table-scroll"><table><thead><tr><th>Zone</th><th>Observed now</th><th>Expected now</th><th>Difference</th><th>Alert threshold</th><th>Signal</th></tr></thead><tbody>{(dashboard.zones || []).map(zone => {
                const delta = Number(zone.current_consumption) - Number(zone.expected_current);
                return <tr key={zone.id}><td><div className="zone-name"><span className={`anomaly-symbol ${zone.anomaly ? 'flagged' : ''}`}><Activity size={14} /></span><span>{zone.name}<small>{Boolean(simulatedCount) ? 'simulated · inherited signal' : 'observed series'}</small></span></div></td><td>{fmt(zone.current_consumption)} <small>{source?.unit || 'units'}</small></td><td>{fmt(zone.expected_current)} <small>{source?.unit || 'units'}</small></td><td className={zone.anomaly ? 'shortage-value' : ''}>{delta > 0 ? '+' : ''}{fmt(delta)} <small>{source?.unit || 'units'}</small></td><td>±{fmt(zone.anomaly_threshold)} <small>{source?.unit || 'units'}</small></td><td><span className={`anomaly-state ${zone.anomaly ? 'flagged' : ''}`}>{zone.anomaly ? `Unusual · ${zone.anomaly_direction || 'review'}` : 'Within threshold'}</span></td></tr>;
              })}</tbody></table>{!(dashboard.zones || []).length && <div className="allocation-empty">No zone-level observations were returned.</div>}</div></div>
            </section>
            {(dashboard.recent_anomalies || []).length > 0 && <details className="panel recent-alerts">
              <summary>Recent unusual readings · {dashboard.recent_anomalies.length} events from the last 72 hours</summary>
              <p>Historical observations beyond the validation-derived error threshold. These are review signals, not confirmed leaks. Up to 20 most recent events shown.</p>
              <div className="table-scroll"><table><thead><tr><th>Observed at</th><th>District</th><th>Observed</th><th>Expected</th><th>Difference</th></tr></thead><tbody>
                {dashboard.recent_anomalies.map((event, i) => <tr key={i}><td>{fullDate(event.timestamp, true, source?.timezone)}</td><td>{event.zone}</td><td>{fmt(event.actual)} {source?.unit}</td><td>{fmt(event.expected)} {source?.unit}</td><td className="shortage-value">{event.deviation > 0 ? '+' : ''}{fmt(event.deviation)} {source?.unit}</td></tr>)}
              </tbody></table></div>
            </details>}
            <section className="planner-section" id="allocation">
              <div className="section-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> DECISION SUPPORT</div><h2>Allocation planner</h2><p>Explore how a declared supply level could cover forecast demand.</p></div><span className="hypothetical-chip">HYPOTHETICAL PLANNING</span></div>
              <div className="planner-grid">
                <div className="panel supply-panel"><div className="panel-heading compact"><div><span className="card-kicker">SUPPLY INPUT</span><h3>Available water</h3></div><span className="user-input-tag">ADJUSTABLE SCENARIO · USER ENTERED</span></div><label className="supply-input-label" htmlFor="supply">Supply for next {horizon} hour{horizon > 1 ? 's' : ''}<span>{source?.unit || 'dataset units'}</span></label><div className="supply-number-wrap"><input id="supply" type="number" min="0" step="any" value={supply} onChange={e => { allocationRequestId.current += 1; setAllocation(null); setAllocLoading(false); setSupply(e.target.value); }} placeholder="Enter available supply" /><span>{source?.unit || 'units'}</span></div><input className="supply-slider" type="range" min="0" max={Math.max(1, Number(dashboard.default_supply || 1) * 2)} step={Math.max(Number(dashboard.default_supply || 1) / 100, 0.01)} value={Math.min(Number(supply) || 0, Math.max(1, Number(dashboard.default_supply || 1) * 2))} onChange={e => { allocationRequestId.current += 1; setAllocation(null); setAllocLoading(false); setSupply(e.target.value); }} aria-label="Adjust available water supply" /><div className="slider-scale"><span>0</span><span>Planning range</span><span>{fmt(Math.max(1, Number(dashboard.default_supply || 1) * 2))}</span></div>
                  <div className="supply-divider" /><div className="supply-result"><div><span>Forecast demand</span><b>{fmt(allocation?.total_demand ?? dashboard.forecast?.reduce((s, x) => s + (Number(x.predicted) || 0), 0))} <small>{source?.unit || 'units'}</small></b></div><div><span>Coverage at this supply</span><b>{allocation ? `${fmt(allocation.coverage_pct, 1)}%` : '—'}</b></div><div><span>Unused supply</span><b>{allocation ? <>{fmt(allocation.unused_supply)} <small>{source?.unit || 'units'}</small></> : '—'}</b></div></div>
                  <p className="planner-note"><CircleHelp size={14} /> Supply is an operator-entered planning assumption; it is not a measured reservoir level.</p>
                </div>
                <div className="panel allocation-panel"><div className="panel-heading compact"><div><span className="card-kicker">PROPOSED SPLIT</span><h3>Coverage by zone</h3></div>{allocLoading ? <span className="updating"><LoaderCircle size={13} className="spin" /> Updating</span> : allocation && <span className="allocation-summary">{fmt(allocation.shortage)} {source?.unit || 'units'} short</span>}</div>
                  {allocError && <div className="inline-error"><AlertCircle size={15} /> {allocError}</div>}
                  {!allocation && !allocError ? <div className="allocation-empty">Allocation appears when the planner responds.</div> : <div className="allocation-bars">{zones.map(zone => <div className="allocation-row" key={zone.id}><div className="allocation-label"><span>{zone.name}</span><b className={`risk-pill ${zone.risk}`}>{zone.risk} risk</b></div><div className="allocation-track"><span style={{ width: `${Math.min(100, Math.max(0, Number(zone.coverage_pct) || 0))}%` }} /></div><div className="allocation-numbers"><span>{fmt(zone.allocation)} <small>of {fmt(zone.demand)}</small></span><b>{fmt(zone.coverage_pct, 0)}%</b></div></div>)}</div>}
                  {allocation?.zones?.some(z => z.explanation) && <div className="planner-explanation"><b>Why this split</b><span>{allocation.zones.filter(z => z.explanation).slice(0, 2).map(z => z.explanation).join(' ')}</span></div>}
                </div>
              </div>
            </section>
            <section className="zones-section" id="zones">
              <div className="section-heading section-heading-tight"><div><div className="eyebrow"><span className="eyebrow-line" /> SERVICE AREAS</div><h2>Zone priorities</h2><p>Adjust priority from 1 (lower) to 5 (higher) for this planning run.{Boolean(simulatedCount) && ' Illustrative zones split one observed series; their alerts are inherited, not independently detected.'}</p></div><span className="zone-count">{zones.length} zones</span></div>
              <div className="zones-layout">
                <div className="panel zones-table-panel"><div className="table-scroll"><table><thead><tr><th>Zone</th><th>Forecast demand</th><th>Priority</th><th>Allocation</th><th>Shortage</th><th>Coverage</th></tr></thead><tbody>{zoneRows.map(zone => <tr key={zone.id}><td><div className="zone-name"><span className="zone-symbol"><Droplets size={14} /></span><span>{zone.name}<small>{zone.risk ? `${zone.risk} risk` : 'Waiting for allocation'}</small></span></div></td><td>{fmt(zone.demand)} <small>{source?.unit || 'units'}</small></td><td><select aria-label={`Priority for ${zone.name}`} className="priority-select" value={priorities[zone.id] ?? zone.priority ?? 3} onChange={e => { allocationRequestId.current += 1; setAllocation(null); setAllocLoading(false); setPriorities(v => ({ ...v, [zone.id]: Number(e.target.value) })); }} >{[1,2,3,4,5].map(p => <option key={p} value={p}>{p} · {p === 1 ? 'Low' : p === 5 ? 'High' : 'Priority'}</option>)}</select></td><td>{fmt(zone.allocation)} <small>{source?.unit || 'units'}</small></td><td className={Number(zone.shortage) > 0 ? 'shortage-value' : ''}>{fmt(zone.shortage)} <small>{source?.unit || 'units'}</small></td><td><span className="coverage-value">{fmt(zone.coverage_pct, 0)}{zone.coverage_pct == null ? '' : '%'}</span></td></tr>)}</tbody></table>{!zoneRows.length && <div className="allocation-empty">No zones are available for this forecast.</div>}</div></div>
                <div className="panel schematic-panel"><div className="schematic-head"><span className="card-kicker">ALL SERVICE AREAS</span><span className="schematic-label">SCHEMATIC · NO GEOGRAPHY</span></div><h3>Metered area overview</h3><p>Illustrative list of observed areas; no locations or pipe routes are shown.</p><div className="zone-network" aria-label="Non-geographic schematic showing all service areas"><div className="network-supply"><Droplets size={15} /><span>Shared forecast supply</span></div><div className="zone-network-grid">{zones.map((zone, i) => <div key={zone.id} className={`zone-network-card ${zone.risk || 'low'}`}><span className="network-index">{String(i + 1).padStart(2, '0')}</span><span className="network-name">{zone.name}</span><span className={`network-risk ${zone.risk || 'low'}`}>{zone.risk || 'pending'} risk</span></div>)}</div></div><div className="schematic-legend"><span><i className="low" /> Lower risk</span><span><i className="medium" /> Medium</span><span><i className="high" /> Higher risk</span></div></div>
              </div>
            </section>
            <section className="evidence-section" id="evidence">
              <div className="section-heading section-heading-tight"><div><div className="eyebrow"><span className="eyebrow-line" /> TRANSPARENCY</div><h2>Model evidence</h2><p>Performance is measured against unseen historical observations.</p></div><span className="evidence-icon"><ShieldCheck size={18} /></span></div>
              <div className="evidence-grid"><div className="panel evidence-detail"><div className="evidence-top"><span className="evidence-mark"><Activity size={17} /></span><div><b>{metrics?.model || 'Forecast model'}</b><span>Compared with a seasonal naive baseline</span></div><span className="evaluation-tag"><Check size={12} /> HELD-OUT</span></div><p>{metrics?.evaluation || 'Model and baseline MAE are evaluated on the same unseen next-hour observations.'} The MAE shown above measures next-hour test predictions only. Longer horizons recursively use forecast values; no 6, 12 or 24-hour accuracy score is claimed.</p><div className="candidate-scores"><span>Next-hour test MAE · {source?.unit || 'dataset units'}</span><b>Model {fmt(metrics?.model_mae, 2)}</b><b>Baseline {fmt(metrics?.baseline_mae, 2)}</b></div><div className="evaluation-stats"><div><span>Training rows</span><b>{fmt(metrics?.training_rows, 0)}</b></div><div><span>Validation rows</span><b>{fmt(metrics?.validation_rows, 0)}</b></div><div><span>Test rows</span><b>{fmt(metrics?.test_rows, 0)}</b></div><div><span>Test window</span><b>{fullDate(metrics?.test_start, false, source?.timezone)} – {fullDate(metrics?.test_end, false, source?.timezone)}</b></div></div></div>
                <div className="panel source-detail"><span className="card-kicker">DATA PROVENANCE</span><h3>{source?.name || 'Dataset source'}</h3><div className="source-facts"><div><span>Observed history</span><b>{fullDate(source?.start, false, source?.timezone)} – {fullDate(source?.end, false, source?.timezone)}</b></div><div><span>Sampling frequency</span><b>{source?.frequency || '—'}{source?.timezone ? ` · ${source.timezone}` : ''}</b></div><div><span>Rows used</span><b>{fmt(source?.rows, 0)}</b></div><div><span>Forecast generated from</span><b>{fullDate(dashboard.forecast_origin, true, source?.timezone)}</b></div></div>{source?.url ? <a href={source.url} target="_blank" rel="noreferrer" className="source-link">View original dataset <ExternalLink size={13} /></a> : <span className="source-link muted">Source link not provided</span>}{source?.notes?.length > 0 && <div className="source-notes">{source.notes.map((note, i) => <span key={i}>{note}</span>)}</div>}</div></div>
            </section>
            <details className="retrain-details" id="setup"><summary><span><b>Data & setup</b><small>Import another CSV or retrain with an available dataset</small></span><ArrowUpRight size={17} /></summary><Onboarding status={status} onRefresh={refreshStatus} retrain /></details>
            <footer className="page-footer"><span>REQU IEM · WATER INTELLIGENCE</span><span>Forecasts support planning; confirm operational decisions with local measurements.</span></footer>
          </>}
        </>}
      </div>
    </main>
  </div>;
}

export default App;
