import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, AlertCircle, ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3,
  Check, ChevronDown, CircleHelp, Droplets, ExternalLink, Gauge, LayoutDashboard,
  LoaderCircle, MapPin, MapPinned, RefreshCw, ShieldCheck, SlidersHorizontal, Waves,
} from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';
import { Onboarding } from './App.jsx';
import AreaMap from './AreaMap.jsx';
import LocationSelectionPage from './LocationSelectionPage.jsx';

const HORIZONS = [1, 6, 12, 24];
const ROUTES = [
  { path: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { path: '/forecasts', label: 'Forecasts', icon: Waves },
  { path: '/map', label: 'Area map', icon: MapPinned },
  { path: '/anomalies', label: 'Anomalies', icon: Activity },
  { path: '/allocation', label: 'Allocation', icon: SlidersHorizontal },
  { path: '/zones', label: 'Zones', icon: MapPinned },
  { path: '/analysis', label: 'Model analysis', icon: BarChart3 },
  { path: '/data', label: 'Data & training', icon: ShieldCheck },
];
const PAGE_META = {
  '/dashboard': ['Operations overview', 'A clear view of demand, supply, and the next decision.'],
  '/forecasts': ['Demand forecasts', 'Explore the district-level outlook by time horizon.'],
  '/map': ['Area map', 'Explore district coverage and watch a forecast scenario evolve.'],
  '/anomalies': ['Unusual consumption', 'Review current and recent readings that differ from expected demand.'],
  '/allocation': ['Allocation planner', 'Test a supply scenario and see how coverage changes by district.'],
  '/zones': ['District priorities', 'Review demand and set the priority weights used by the planner.'],
  '/analysis': ['Model analysis', 'Inspect held-out evidence and the limits of each evaluation.'],
  '/data': ['Data & training', 'Review source details, import a CSV, or retrain the local model.'],
};

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map(x => x.msg || x.message || JSON.stringify(x)).join('; ') : body.detail || body.message;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return body;
}
const number = (value, digits = 1) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
function date(value, timezone = 'UTC', time = false) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const options = time
    ? { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric' };
  if (timezone && timezone !== 'source local time') options.timeZone = timezone;
  try { return d.toLocaleString(undefined, options); }
  catch { delete options.timeZone; return d.toLocaleString(undefined, options); }
}
function tickDate(value, timezone = 'UTC') {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const options = { month: 'short', day: 'numeric', hour: 'numeric' };
  if (timezone && timezone !== 'source local time') options.timeZone = timezone;
  try { return d.toLocaleString(undefined, options); }
  catch { delete options.timeZone; return d.toLocaleString(undefined, options); }
}
function NavSidebar({ ready }) {
  return <aside className="sidebar route-sidebar">
    <NavLink className="brand" to="/" aria-label="Requiem water intelligence home"><span className="brand-mark"><Droplets size={21} /></span><span><strong>requiem</strong><small>WATER INTELLIGENCE</small></span></NavLink>
    <div className="side-label">OPERATIONS</div>
    <nav className="side-nav" aria-label="Main navigation">{ROUTES.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} aria-label={label} className={({ isActive }) => isActive ? 'selected' : ''}><Icon size={17} /><span>{label}</span></NavLink>)}</nav>
    <div className="sidebar-spacer" />
    <div className="sidebar-status"><span className={`status-orb ${ready ? 'is-ready' : ''}`} /><div><strong>{ready ? 'Model ready' : 'Dataset required'}</strong><span>{ready ? 'Local forecast service' : 'Import data to begin'}</span></div></div>
    <div className="sidebar-foot">LOCAL OPERATIONS CONSOLE <span>v1.0</span></div>
  </aside>;
}
function Metric({ label, value, unit, note, icon: Icon, tone = 'teal' }) {
  return <article className="metric-card"><div className={`metric-icon ${tone}`}><Icon size={17} /></div><div className="metric-label">{label}</div><div className="metric-value">{value}<span>{unit}</span></div><div className="metric-note">{note}</div></article>;
}
function PageTitle({ title, description, actions }) {
  return <section className="page-heading route-page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> WATER OPERATIONS</div><h1>{title}</h1><p>{description}</p></div>{actions && <div className="heading-actions">{actions}</div>}</section>;
}
function SectionTitle({ eyebrow, title, description, right }) {
  return <div className="section-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> {eyebrow}</div><h2>{title}</h2>{description && <p>{description}</p>}</div>{right}</div>;
}
function Notice({ children, retry }) {
  return <div className="notice error"><AlertCircle size={17} /><span>{children}</span>{retry && <button onClick={retry}>Retry</button>}</div>;
}
function Loading({ label = 'Loading operational data…' }) {
  return <div className="loading-card"><LoaderCircle size={20} className="spin" /> {label}</div>;
}
function SourceBar({ source }) {
  if (!source) return null;
  return <div className="source-strip"><span className="source-icon"><Waves size={16} /></span><div className="source-info"><b>{source.name}</b><span>{source.frequency || 'Observed history'}{source.timezone ? ` · ${source.timezone}` : ''} <i /> {number(source.rows, 0)} rows <i /> {date(source.start, source.timezone)} – {date(source.end, source.timezone)}</span></div><div className="source-tags"><span className="source-tag">{number(source.observed_zones, 0)} measured districts</span><span className="source-unit">Unit: {source.unit || 'dataset units'}</span></div></div>;
}
function SeriesChart({ data, unit, timezone = 'UTC', baseline = false, compact = false }) {
  return <div className={`chart-container ${compact ? 'compact-chart' : ''}`}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={data} margin={{ top: 18, right: 12, left: 0, bottom: 0 }}><CartesianGrid vertical={false} stroke="#edf0ed" strokeDasharray="3 5" /><XAxis dataKey="timestamp" tickFormatter={v => tickDate(v, timezone)} tickLine={false} axisLine={false} minTickGap={35} tick={{ fill: '#909a96', fontSize: 11 }} /><YAxis tickLine={false} axisLine={false} width={55} tick={{ fill: '#909a96', fontSize: 11 }} /><Tooltip labelFormatter={v => date(v, timezone, true)} formatter={(v, name) => [`${number(v, 2)} ${unit}`, name]} /><Legend verticalAlign="bottom" height={28} wrapperStyle={{ fontSize: 11, color: '#718078' }} /><Line dataKey="actual" name="Observed" stroke="#208b79" strokeWidth={2.3} dot={false} connectNulls={false} /><Line dataKey="predicted" name="Forecast" stroke="#e89a58" strokeWidth={2.3} strokeDasharray="5 4" dot={{ r: 3 }} connectNulls={false} />{baseline && <Line dataKey="baseline" name="Weekly baseline" stroke="#7290a0" strokeWidth={1.8} strokeDasharray="3 4" dot={false} connectNulls={false} />}</ComposedChart></ResponsiveContainer></div>;
}
function ForecastTable({ forecast, unit, timezone }) {
  return <div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Forecast time</th><th>Predicted demand</th></tr></thead><tbody>{(forecast || []).map((p, i) => <tr key={`${p.timestamp}-${i}`}><td>{date(p.timestamp, timezone, true)}</td><td>{number(p.predicted, 2)} {unit}</td></tr>)}</tbody></table>{!forecast?.length && <div className="allocation-empty">No forecast points returned.</div>}</div></div>;
}
function AlertsTable({ zones, recent = [], unit, timezone }) {
  return <>
    <div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>District</th><th>Observed now</th><th>Expected now</th><th>Difference</th><th>Alert threshold</th><th>Signal</th></tr></thead><tbody>{(zones || []).map(z => { const delta = Number(z.current_consumption) - Number(z.expected_current); return <tr key={z.id}><td>{z.name}</td><td>{number(z.current_consumption, 2)} {unit}</td><td>{number(z.expected_current, 2)} {unit}</td><td className={z.anomaly ? 'shortage-value' : ''}>{delta > 0 ? '+' : ''}{number(delta, 2)} {unit}</td><td>±{number(z.anomaly_threshold, 2)} {unit}</td><td><span className={`anomaly-state ${z.anomaly ? 'flagged' : ''}`}>{z.anomaly ? `Unusual · ${z.anomaly_direction || 'review'}` : 'Within threshold'}</span></td></tr>; })}</tbody></table>{!zones?.length && <div className="allocation-empty">No current district readings are available.</div>}</div></div>
    {recent.length > 0 && <details className="panel recent-alerts"><summary>Recent unusual readings · {recent.length} events</summary><p>Historical review signals from the last 72 hours. These are not confirmed leaks.</p><div className="table-scroll"><table><thead><tr><th>Observed at ({timezone})</th><th>District</th><th>Observed</th><th>Expected</th><th>Difference</th></tr></thead><tbody>{recent.map((e, i) => <tr key={`${e.timestamp}-${i}`}><td>{date(e.timestamp, timezone, true)}</td><td>{e.zone}</td><td>{number(e.actual, 2)} {unit}</td><td>{number(e.expected, 2)} {unit}</td><td className="shortage-value">{e.deviation > 0 ? '+' : ''}{number(e.deviation, 2)} {unit}</td></tr>)}</tbody></table></div></details>}
  </>;
}
function ZoneTable({ zones, priorities, setPriorities, unit }) {
  return <div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>District</th><th>Forecast demand</th><th>Current vs expected</th><th>Priority</th></tr></thead><tbody>{(zones || []).map(z => <tr key={z.id}><td>{z.name}</td><td>{number(z.predicted_demand, 2)} {unit}</td><td>{number(z.current_consumption, 2)} / {number(z.expected_current, 2)} {unit}{z.anomaly && <span className="risk-pill high"> Unusual</span>}</td><td><select aria-label={`Priority for ${z.name}`} className="priority-select" value={priorities[z.id] ?? z.priority ?? 3} onChange={e => setPriorities(v => ({ ...v, [z.id]: Number(e.target.value) }))}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n} · {n === 1 ? 'Lower' : n === 5 ? 'Higher' : 'Priority'}</option>)}</select></td></tr>)}</tbody></table>{!zones?.length && <div className="allocation-empty">No district data available.</div>}</div></div>;
}
function AllocationResults({ allocation, unit }) {
  if (!allocation) return <div className="panel allocation-empty">Allocation results appear when the API responds.</div>;
  return <><div className="metrics-grid allocation-metrics"><Metric label="Forecast demand" value={number(allocation.total_demand)} unit={` ${unit}`} note="Selected horizon" icon={Droplets} /><Metric label="Available supply" value={number(allocation.supply)} unit={` ${unit}`} note="Operator-entered scenario" icon={Waves} tone="navy" /><Metric label="Uncovered shortage" value={number(allocation.shortage)} unit={` ${unit}`} note="Demand without coverage" icon={AlertCircle} tone="orange" /><Metric label="Unused supply" value={number(allocation.unused_supply)} unit={` ${unit}`} note="Remaining after demand is met" icon={Check} /></div><div className="panel allocation-panel"><div className="panel-heading"><div><span className="card-kicker">PROPOSED SPLIT</span><h2>Coverage by district</h2></div><b>{number(allocation.coverage_pct, 1)}% covered</b></div><div className="allocation-bars">{allocation.zones.map(z => <div className="allocation-row" key={z.id}><div className="allocation-label"><span>{z.name}</span><b className={`risk-pill ${z.risk}`}>{z.risk} risk</b></div><div className="allocation-track"><span style={{ width: `${Math.min(100, Math.max(0, Number(z.coverage_pct) || 0))}%` }} /></div><div className="allocation-numbers"><span>{number(z.allocation)} of {number(z.demand)} {unit}</span><b>{number(z.coverage_pct, 0)}%</b></div><p className="planner-explanation">{z.explanation}</p></div>)}</div></div></>;
}
function AnalysisPage({ data, loading, error, onRefresh, selectedZone, setSelectedZone }) {
  const unit = data?.unit || 'dataset units';
  const timezone = data?.timezone || 'UTC';
  const zones = data?.zones || [];
  const selected = zones.find(z => z.id === selectedZone) || zones[0];
  const featureRows = data?.feature_importance || [];
  return <>
    <PageTitle title="Model analysis" description="Held-out evaluation and district-level evidence." actions={<button className="icon-button" onClick={onRefresh} title="Refresh analysis"><RefreshCw size={16} /></button>} />
    {loading && !data ? <Loading label="Loading cached model evidence…" /> : error ? <Notice retry={onRefresh}>{error}</Notice> : data && <>
      <div className="notice info"><ShieldCheck size={17} /><span>Independent chronological holdout from the uploaded district history. Evaluation is separate from the source competition score.</span></div>
      <div className="metrics-grid"><Metric label="Overall MAE" value={number(data.overall.mae, 3)} unit={` ${unit}`} note="Next-hour test predictions · microaverage" icon={Gauge} tone="navy" /><Metric label="RMSE" value={number(data.overall.rmse, 3)} unit={` ${unit}`} note="Larger errors receive more weight" icon={Activity} tone="sand" /><Metric label="Bias" value={number(data.overall.bias, 3)} unit={` ${unit}`} note="Positive means overprediction" icon={ArrowUpRight} tone="teal" /><Metric label="Baseline MAE" value={number(data.overall.baseline_mae, 3)} unit={` ${unit}`} note={`${number(data.overall.improvement_pct, 1)}% improvement vs baseline`} icon={ArrowDownRight} /></div>
      <section className="analysis-section"><SectionTitle eyebrow="HELD-OUT DETAIL" title="District test performance" description="Models were fitted before the test window; scores are computed on later observed hours." right={<span className="source-tag">{number(data.overall.samples, 0)} district-hour rows</span>} /><div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>District</th><th>Validation model MAE</th><th>Validation baseline MAE</th><th>Test MAE</th><th>Test RMSE</th><th>Bias</th><th>Weekly baseline MAE</th><th>Improvement</th><th>Samples</th></tr></thead><tbody>{zones.map(z => <tr key={z.id}><td>{z.name}</td><td>{number(z.validation_model_mae, 3)} {unit}</td><td>{number(z.validation_baseline_mae, 3)} {unit}</td><td>{number(z.mae, 3)} {unit}</td><td>{number(z.rmse, 3)} {unit}</td><td>{number(z.bias, 3)} {unit}</td><td>{number(z.baseline_mae, 3)} {unit}</td><td>{number(z.improvement_pct, 1)}%</td><td>{number(z.samples, 0)}</td></tr>)}</tbody></table></div></div><p className="analysis-note">Overall scores pool district-hour rows. District scores do not average evenly when districts have different sample counts. The reported holdout is independent of the original competition evaluation.</p></section>
      <section className="analysis-section"><SectionTitle eyebrow="SCORED TEST HOURS" title="Observed vs predicted" description={`Up to 168 scored test-hour readings for one district, shown in ${timezone}.`} /><div className="analysis-controls"><label className="field-label">Select district<select value={selected?.id || ''} onChange={e => setSelectedZone(e.target.value)}>{zones.map(z => <option key={z.id} value={z.id}>{z.name}</option>)}</select></label><span className="source-tag">Test window: {date(data.split.test_start, timezone)} – {date(data.split.test_end, timezone)} · {timezone}</span></div>{selected?.history?.length ? <div className="panel"><SeriesChart data={selected.history} unit={unit} timezone={timezone} baseline /></div> : <div className="panel allocation-empty">No held-out history was saved for this district.</div>}</section>
      <section className="analysis-section"><SectionTitle eyebrow="ERROR SHAPE" title="Error by hour of day" description={`Next-hour MAE by ${timezone} hour, compared with the weekly seasonal baseline.`} /><div className="panel analysis-chart"><ResponsiveContainer width="100%" height={250}><BarChart data={data.hourly_errors || []} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}><CartesianGrid vertical={false} stroke="#edf0ed" strokeDasharray="3 5" /><XAxis dataKey="hour" tickFormatter={h => `${String(h).padStart(2, '0')}:00`} tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} /><Tooltip formatter={(v, name) => [`${number(v, 3)} ${unit}`, name]} labelFormatter={h => `${String(h).padStart(2, '0')}:00 ${timezone}`} /><Legend verticalAlign="bottom" height={28} wrapperStyle={{ fontSize: 11, color: '#718078' }} /><Bar dataKey="mae" name="Model MAE" fill="#258d79" radius={[3,3,0,0]} /><Bar dataKey="baseline_mae" name="Weekly baseline MAE" fill="#e4a166" radius={[3,3,0,0]} /></BarChart></ResponsiveContainer></div></section>
      <section className="analysis-section"><SectionTitle eyebrow="FEATURE DIAGNOSTIC" title={featureRows.length ? 'Validation permutation importance' : 'Model inputs and limitations'} description={featureRows.length ? 'Measured on the validation window only; this is not a causal explanation.' : 'Permutation importance was not computed for this model.'} />{featureRows.length ? <div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Feature</th><th>MAE increase after shuffling</th></tr></thead><tbody>{featureRows.map(row => <tr key={row.feature}><td>{row.label || row.feature}</td><td>{number(row.mae_increase, 4)} {unit}</td></tr>)}</tbody></table></div></div> : <div className="notice info"><CircleHelp size={17} /><span>{data.feature_importance_note || 'Permutation importance is not available in this model artifact. No feature contribution estimate is reported.'}</span></div>}</section>
      <section className="analysis-section"><SectionTitle eyebrow="LIMITED ROLLOUT CHECK" title="Multi-hour horizon backtest" description="Separate from the full rolling next-hour test score." />{data.horizon_backtest_note && <p className="analysis-note">{data.horizon_backtest_note}</p>}<div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Horizon</th><th>Hourly MAE</th><th>Baseline MAE</th><th>Improvement</th><th>Hourly samples</th><th>Origins</th><th>Total-volume MAE</th><th>Baseline volume MAE</th></tr></thead><tbody>{(data.horizon_backtest || []).map(row => <tr key={row.hours}><td>{row.hours}h</td><td>{number(row.mae, 3)} {unit}</td><td>{number(row.baseline_mae, 3)} {unit}</td><td>{number(row.improvement_pct, 1)}%</td><td>{number(row.samples, 0)}</td><td>{number(row.origins, 0)}</td><td>{row.volume_mae == null ? '—' : `${number(row.volume_mae, 3)} ${unit}`}</td><td>{row.baseline_volume_mae == null ? '—' : `${number(row.baseline_volume_mae, 3)} ${unit}`}</td></tr>)}</tbody></table></div></div><p className="analysis-note">Rollouts use fixed models and up to eight predetermined weekly origins inside the test period. Actual future readings are never fed into a rollout. Hourly MAE pools errors at each future hour; volume MAE (when present) compares total demand per rollout. These limited origins are not the same as the full next-hour test window.</p></section>
      {data.notes?.length > 0 && <section className="analysis-section"><SectionTitle eyebrow="METHOD NOTES" title="Read the results carefully" /><ul className="analysis-notes">{data.notes.map((note, i) => <li key={i}>{note}</li>)}</ul></section>}
      {data.references?.length > 0 && <section className="analysis-section"><SectionTitle eyebrow="REFERENCES" title="Source material" /><div className="reference-grid">{data.references.map(ref => <a className="panel reference-card" href={ref.url} target="_blank" rel="noreferrer" key={ref.url}><b>{ref.name}</b><span>{ref.purpose}</span><ExternalLink size={14} /></a>)}</div></section>}
      <div className="analysis-split">Training begins {date(data.split.train_start, timezone)} · Validation begins {date(data.split.validation_start, timezone)} · Test {date(data.split.test_start, timezone)} – {date(data.split.test_end, timezone)} · timestamps {timezone}.</div>
    </>}
  </>;
}

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const path = PAGE_META[location.pathname] ? location.pathname : '/dashboard';
  const [status, setStatus] = useState(null), [statusError, setStatusError] = useState('');
  const [dashboard, setDashboard] = useState(null), [dashLoading, setDashLoading] = useState(false), [dashError, setDashError] = useState('');
  const [horizon, setHorizon] = useState(1), [supply, setSupply] = useState(''), [priorities, setPriorities] = useState({}), [allocation, setAllocation] = useState(null), [allocLoading, setAllocLoading] = useState(false), [allocError, setAllocError] = useState('');
  const [forecastDistrict, setForecastDistrict] = useState('all'), [districtSeries, setDistrictSeries] = useState(null), [seriesLoading, setSeriesLoading] = useState(false), [seriesError, setSeriesError] = useState('');
  const [analysis, setAnalysis] = useState(null), [analysisLoading, setAnalysisLoading] = useState(false), [analysisError, setAnalysisError] = useState(''), [analysisDistrict, setAnalysisDistrict] = useState('');
  const [operatingLocation] = useState(() => {
    try { return JSON.parse(window.localStorage.getItem('requiem-location') || 'null'); }
    catch { return null; }
  });
  const dashboardId = useRef(0), allocationId = useRef(0), seriesId = useRef(0), analysisId = useRef(0), allocationTimer = useRef(), wasTraining = useRef(false);
  const ready = Boolean(status?.ready);
  const source = dashboard?.source;
  const unit = source?.unit || 'dataset units';
  const timezone = source?.timezone || 'UTC';

  const refreshStatus = useCallback(async () => { try { const result = await api('/status'); setStatus(result); setStatusError(''); return result; } catch (e) { setStatusError(e.message); return null; } }, []);
  const loadDashboard = useCallback(async (h = horizon) => {
    const id = ++dashboardId.current; allocationId.current++; setAllocation(null); setAllocLoading(false); setDashLoading(true); setDashError('');
    try {
      const d = await api(`/dashboard?horizon=${h}`);
      if (id !== dashboardId.current) return null;
      setDashboard(d); setSupply(v => v === '' ? String(d.default_supply ?? '') : v);
      setPriorities(current => { const ids = new Set((d.zones || []).map(z => z.id)); const next = Object.fromEntries(Object.entries(current).filter(([k]) => ids.has(k))); d.zones?.forEach(z => { if (next[z.id] == null) next[z.id] = z.priority || 3; }); return next; });
      return d;
    } catch (e) { if (id === dashboardId.current) { setDashError(e.message); setDashboard(null); setAllocation(null); } return null; }
    finally { if (id === dashboardId.current) setDashLoading(false); }
  }, [horizon]);
  const loadAnalysis = useCallback(async () => {
    const id = ++analysisId.current; setAnalysisLoading(true); setAnalysisError('');
    try { const a = await api('/analysis'); if (id === analysisId.current) { setAnalysis(a); if (!a.zones?.some(z => z.id === analysisDistrict)) setAnalysisDistrict(a.zones?.[0]?.id || ''); } }
    catch (e) { if (id === analysisId.current) { setAnalysis(null); setAnalysisError(e.message); } }
    finally { if (id === analysisId.current) setAnalysisLoading(false); }
  }, [analysisDistrict]);
  const loadAllocation = useCallback(async () => {
    const id = ++allocationId.current;
    if (!dashboard || dashboard.horizon !== horizon || supply === '' || !Number.isFinite(Number(supply)) || Number(supply) < 0) { setAllocation(null); setAllocError(supply !== '' && Number(supply) < 0 ? 'Supply must be zero or greater.' : ''); setAllocLoading(false); return; }
    setAllocLoading(true); setAllocError('');
    try { const a = await api('/allocate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ horizon, supply: Number(supply), priorities, demand_multipliers: {} }) }); if (id === allocationId.current) setAllocation(a); }
    catch (e) { if (id === allocationId.current) { setAllocation(null); setAllocError(e.message); } }
    finally { if (id === allocationId.current) setAllocLoading(false); }
  }, [dashboard, supply, horizon, priorities]);

  useEffect(() => { refreshStatus(); }, [refreshStatus]);
  useEffect(() => { if (!status?.training) return undefined; const t = setInterval(refreshStatus, 2000); return () => clearInterval(t); }, [status?.training, refreshStatus]);
  useEffect(() => { if (ready) { loadDashboard(horizon); loadAnalysis(); } else { dashboardId.current++; analysisId.current++; setDashboard(null); setAnalysis(null); } }, [ready]);
  useEffect(() => { if (!ready) return; setSupply(''); setAllocation(null); loadDashboard(horizon); }, [horizon]);
  useEffect(() => { if (status?.training) wasTraining.current = true; else if (wasTraining.current && ready) { wasTraining.current = false; loadDashboard(horizon); loadAnalysis(); } }, [status?.training, ready]);
  useEffect(() => {
    clearTimeout(allocationTimer.current);
    if (!dashboard || dashboard.horizon !== horizon || supply === '' || !Number.isFinite(Number(supply)) || Number(supply) < 0) { allocationId.current++; setAllocation(null); setAllocLoading(false); return undefined; }
    setAllocation(null);
    allocationTimer.current = setTimeout(loadAllocation, 250);
    return () => { clearTimeout(allocationTimer.current); allocationId.current++; };
  }, [dashboard, supply, priorities, horizon, loadAllocation]);
  useEffect(() => {
    if (!ready || path !== '/forecasts' || forecastDistrict === 'all') { seriesId.current++; setDistrictSeries(null); return undefined; }
    const id = ++seriesId.current; setSeriesLoading(true); setSeriesError('');
    api(`/zone-series?zone_id=${encodeURIComponent(forecastDistrict)}&horizon=${horizon}`).then(result => { if (id === seriesId.current) setDistrictSeries(result); }).catch(e => { if (id === seriesId.current) { setDistrictSeries(null); setSeriesError(e.message); } }).finally(() => { if (id === seriesId.current) setSeriesLoading(false); });
    return () => { seriesId.current++; };
  }, [ready, path, forecastDistrict, horizon, dashboard]);
  useEffect(() => { if (location.hash === '#evidence') navigate('/analysis', { replace: true }); }, [location.hash, navigate]);

  if (location.pathname === '/' || location.pathname === '/welcome' || location.pathname === '/location') return <LocationSelectionPage />;

  const allocationZones = allocation?.zones || [];
  const allPoints = useMemo(() => [...(dashboard?.history || []).map(x => ({ timestamp: x.timestamp, actual: x.actual })), ...(dashboard?.forecast || []).map(x => ({ timestamp: x.timestamp, predicted: x.predicted }))], [dashboard]);
  const seriesPoints = useMemo(() => {
    if (forecastDistrict === 'all' || !districtSeries) return allPoints;
    return [...(districtSeries.history || []).map(x => ({ timestamp: x.timestamp, actual: x.actual })), ...(districtSeries.forecast || []).map(x => ({ timestamp: x.timestamp, predicted: x.predicted }))];
  }, [forecastDistrict, districtSeries, allPoints]);
  const pageMeta = PAGE_META[path];
  const pageLoading = !ready || (dashLoading && !dashboard);

  return <div className="app-shell">
    <NavSidebar ready={ready} />
    <main className="main-area">
      <header className="topbar"><div className="breadcrumb">Water operations <span>/</span> <b>{pageMeta[0]}</b></div><div className="topbar-right"><span className="local-chip"><span className="live-dot" /> LOCAL INSTANCE</span>{operatingLocation?.name && <span className="operating-location-chip"><MapPin size={12} /> {operatingLocation.name}</span>}{ready && <div className="horizon-control"><label htmlFor="global-horizon">HORIZON</label><select id="global-horizon" value={horizon} onChange={e => setHorizon(Number(e.target.value))}>{HORIZONS.map(h => <option key={h} value={h}>{h} hour{h > 1 ? 's' : ''}</option>)}</select><ChevronDown size={14} /></div>}<button className="icon-button" onClick={() => { refreshStatus(); if (path === '/analysis') loadAnalysis(); else loadDashboard(horizon); }} title="Refresh this page" aria-label="Refresh this page"><RefreshCw size={16} /></button></div></header>
      <div className="page-content route-content">
        {path !== '/analysis' && <PageTitle title={pageMeta[0]} description={pageMeta[1]} />}
        {statusError && <Notice retry={refreshStatus}>Can’t reach the local API: {statusError}</Notice>}
        {dashError && ready && <Notice retry={() => loadDashboard(horizon)}>{dashError}</Notice>}
        {path !== '/data' && !ready && <div className="data-required"><div className="empty-data-mark"><Droplets size={22} /></div><h2>Connect a water dataset first</h2><p>Import hourly historical readings and train the local model to unlock this page.</p><Link className="primary-button" to="/data">Go to data & training <ArrowRight size={15} /></Link></div>}
        {path !== '/data' && ready && pageLoading && <Loading />}

        {path === '/dashboard' && ready && dashboard && <>
          <SourceBar source={source} />
          <div className="metrics-grid"><Metric label="Forecast demand" value={number(dashboard.forecast?.reduce((s, x) => s + x.predicted, 0))} unit={` ${unit}`} note={`Next ${horizon} hour${horizon > 1 ? 's' : ''}`} icon={Droplets} /><Metric label="Declared supply" value={supply === '' ? '—' : number(supply)} unit={` ${unit}`} note="Current adjustable scenario" icon={Waves} tone="navy" /><Metric label="Uncovered shortage" value={number(allocation?.shortage)} unit={` ${unit}`} note={allocation ? `${number(allocation.coverage_pct, 1)}% demand covered` : 'Allocation pending'} icon={AlertCircle} tone="orange" /><Metric label="Current alerts" value={number(dashboard.zones?.filter(z => z.anomaly).length, 0)} unit="" note="Observed vs expected consumption" icon={Activity} /></div>
          <section className="panel chart-panel"><div className="panel-heading"><div><span className="card-kicker">DEMAND SIGNAL</span><h2>Recent demand and outlook</h2><p>Observed readings and the {horizon}-hour forecast · {unit}</p></div><Link className="text-link" to="/forecasts">Explore forecasts <ArrowRight size={14} /></Link></div><SeriesChart data={allPoints} unit={unit} timezone={timezone} compact /></section>
          <div className="route-link-grid">{ROUTES.slice(1).map(({ path: to, label, icon: Icon }) => <Link className="route-link-card" key={to} to={to}><span><Icon size={17} /></span><b>{label}</b><ArrowRight size={15} /></Link>)}</div>
        </>}

        {path === '/forecasts' && ready && dashboard && <>
          <SourceBar source={source} /><section className="panel chart-panel"><div className="panel-heading"><div><span className="card-kicker">HOURLY DEMAND</span><h2>{forecastDistrict === 'all' ? 'All measured districts' : districtSeries?.name || 'Selected district'}</h2><p>Observed history and recursive forecast · {districtSeries?.unit || unit} · {districtSeries?.timezone || timezone}</p></div><label className="field-label route-select-label">Forecast series<select value={forecastDistrict} onChange={e => setForecastDistrict(e.target.value)}><option value="all">All measured districts</option>{(dashboard.zones || []).map(z => <option key={z.id} value={z.id}>{z.name}</option>)}</select></label></div>{seriesError && <Notice>{seriesError}</Notice>}{seriesLoading ? <Loading label="Loading district forecast…" /> : <SeriesChart data={seriesPoints} unit={districtSeries?.unit || unit} timezone={districtSeries?.timezone || timezone} />}</section><SectionTitle eyebrow="UPCOMING HOURS" title="Forecast points" description={`Demand is summed per hour in ${districtSeries?.unit || unit}.`} /><ForecastTable forecast={forecastDistrict === 'all' ? dashboard.forecast : districtSeries?.forecast} unit={districtSeries?.unit || unit} timezone={districtSeries?.timezone || timezone} />
        </>}

        {path === '/anomalies' && ready && dashboard && <><SourceBar source={source} /><div className="notice info"><Activity size={17} /><span>Latest observed readings are compared with predictions made without those targets. Alerts are review signals, not confirmed leaks.</span></div><AlertsTable zones={dashboard.zones || []} recent={dashboard.recent_anomalies || []} unit={unit} timezone={timezone} /></>}

        {path === '/allocation' && ready && dashboard && <><SourceBar source={source} /><div className="allocation-route-grid"><div className="panel supply-panel"><span className="card-kicker">ADJUSTABLE PLANNING SCENARIO</span><h2>Available supply</h2><p>Operator-entered assumption for the selected {horizon}-hour window.</p><label className="field-label" htmlFor="supply-input">Supply · {unit}<input id="supply-input" type="number" min="0" step="any" value={supply} onChange={e => { allocationId.current++; setAllocation(null); setSupply(e.target.value); }} /></label><input className="supply-slider" type="range" min="0" max={Math.max(1, Number(dashboard.default_supply || 1) * 2)} step="any" value={Math.min(Number(supply) || 0, Math.max(1, Number(dashboard.default_supply || 1) * 2))} onChange={e => { allocationId.current++; setAllocation(null); setSupply(e.target.value); }} aria-label="Adjust available supply" /><div className="slider-scale"><span>0</span><span>Scenario range</span><span>{number(Number(dashboard.default_supply || 1) * 2)}</span></div>{allocError && <Notice>{allocError}</Notice>}<p className="planner-note"><CircleHelp size={14} /> This is not a measured reservoir or infrastructure capacity.</p>{allocLoading && <span className="updating"><LoaderCircle size={14} className="spin" /> Updating allocation</span>}</div><div><AllocationResults allocation={allocation} unit={unit} />{!allocation && !allocLoading && <p className="analysis-note">Choose a valid supply amount to calculate coverage.</p>}</div></div><SectionTitle eyebrow="DISTRICT WEIGHTS" title="Priorities" description="Weights range from 1 (lower) to 5 (higher). Adjustments recalculate the shared allocation." /><ZoneTable zones={dashboard.zones || []} priorities={priorities} setPriorities={setPriorities} unit={unit} /></>}

        {path === '/zones' && ready && dashboard && <><SourceBar source={source} /><ZoneTable zones={dashboard.zones || []} priorities={priorities} setPriorities={setPriorities} unit={unit} /><section className="panel zone-network-page"><SectionTitle eyebrow="AREA INDEX" title="All measured districts" description="Each row is a dataset zone; displayed order carries no geographic meaning." /><div className="zone-network-grid">{(dashboard.zones || []).map((z, i) => <div className={`zone-network-card ${z.anomaly ? 'high' : 'low'}`} key={z.id}><span className="network-index">{String(i + 1).padStart(2, '0')}</span><span className="network-name">{z.name}</span><span className="network-risk">{z.anomaly ? 'Current alert' : 'No current alert'}</span></div>)}</div></section></>}

        {path === '/map' && ready && dashboard && <AreaMap dashboard={dashboard} allocation={allocation} supply={supply} onSupplyChange={value => { allocationId.current++; setAllocation(null); setSupply(value); }} priorities={priorities} onPriorityChange={(id, value) => { allocationId.current++; setAllocation(null); setPriorities(old => ({...old, [id]: value})); }} horizon={horizon} busy={allocLoading || dashLoading || dashboard.horizon !== horizon} error={allocError} />}
        {path === '/analysis' && <AnalysisPage data={analysis} loading={analysisLoading} error={analysisError} onRefresh={loadAnalysis} selectedZone={analysisDistrict} setSelectedZone={setAnalysisDistrict} />}
        {path === '/data' && <><Onboarding status={status} onRefresh={refreshStatus} /><SourceBar source={source} />{source && <section className="panel source-detail route-source-detail"><span className="card-kicker">SOURCE DETAILS</span><h2>{source.name}</h2><div className="source-facts"><div><span>Frequency & timezone</span><b>{source.frequency || '—'} · {source.timezone || 'UTC'}</b></div><div><span>Coverage</span><b>{date(source.start, source.timezone)} – {date(source.end, source.timezone)}</b></div><div><span>Measured districts</span><b>{number(source.observed_zones, 0)}</b></div><div><span>Unit</span><b>{source.unit || 'dataset units'}</b></div><div><span>Rows</span><b>{number(source.rows, 0)}</b></div></div>{source.url && <a className="source-link" href={source.url} target="_blank" rel="noreferrer">Original dataset <ExternalLink size={14} /></a>}{source.notes?.length > 0 && <div className="source-notes">{source.notes.map((n, i) => <span key={i}>{n}</span>)}</div>}</section>}</>}
        {ready && <footer className="page-footer"><span>REQUIEM · WATER INTELLIGENCE</span><span>Forecasts support planning; confirm operational decisions with local measurements.</span></footer>}
      </div>
    </main>
  </div>;
}

export default App;
