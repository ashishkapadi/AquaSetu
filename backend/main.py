import json
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict

from .allocation import allocate
from .data import inspect_csv
from .forecasting import train, dashboard

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
ARTIFACTS = ROOT / 'artifacts'
DATA.mkdir(exist_ok=True)
ARTIFACTS.mkdir(exist_ok=True)
app = FastAPI(title='Requiem Water Intelligence', version='1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

state = {'training': False, 'error': None, 'result': None}
lock = threading.Lock()
cached = ARTIFACTS / 'dashboard.json'
if cached.exists():
    try:
        state['result'] = json.loads(cached.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        state['error'] = 'Could not load the saved model results. Please retrain.'


class TrainingRequest(BaseModel):
    filename: str
    timestamp_column: str
    target_column: str
    zone_column: str | None = None
    unit: str = Field(default='dataset units', max_length=60)


class AllocationRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    horizon: Literal[1, 6, 12, 24] = 1
    supply: float = Field(ge=0, le=1e15)
    priorities: dict[str, float] = Field(default_factory=dict)
    demand_multipliers: dict[str, float] = Field(default_factory=dict)


class MapTimelineRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    hourly_supply: float = Field(ge=0, le=1e15)
    priorities: dict[str, float] = Field(default_factory=dict)


def data_path(name):
    if not name or Path(name).name != name or '/' in name or '\\' in name:
        raise HTTPException(400, 'Use a CSV filename without a directory path.')
    path = (DATA / name).resolve()
    if path.parent != DATA.resolve() or path.suffix.lower() != '.csv':
        raise HTTPException(400, 'Only CSV files inside the data folder are supported.')
    return path


@app.get('/api/status')
def status():
    files = []
    for file in sorted(DATA.glob('*.csv')):
        try:
            files.append(inspect_csv(file))
        except Exception:
            files.append(dict(name=file.name, columns=[], rows_preview=0, error='Could not parse this CSV.'))
    return dict(ready=state['result'] is not None, training=state['training'],
                error=state['error'], files=files,
                message='Training and evaluating on chronological data…' if state['training'] else
                        'Forecast ready.' if state['result'] else 'Import an hourly consumption CSV to train your first model.')


@app.post('/api/upload')
async def upload(file: UploadFile = File(...)):
    path = data_path(file.filename)
    with lock:
        if state['training']:
            raise HTTPException(409, 'Wait for training to finish before replacing data.')
    if path.exists():
        stem = path.stem
        number = 2
        while path.exists():
            path = DATA / f'{stem}-{number}.csv'
            number += 1
    size = 0
    temp = path.with_suffix('.upload')
    try:
        with temp.open('wb') as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    raise HTTPException(413, 'CSV exceeds the 50 MB limit.')
                out.write(chunk)
        info = inspect_csv(temp)
        temp.replace(path)
        return {**info, 'name': path.name}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, 'Could not read this CSV. Check its delimiter, encoding and header row.') from exc
    finally:
        if temp.exists():
            temp.unlink()


def run_training(path, request):
    try:
        result = train(path, request.timestamp_column, request.target_column,
                       request.zone_column or None, request.unit, ARTIFACTS)
        with lock:
            state['result'] = result
            state['error'] = None
    except Exception as exc:
        with lock:
            state['error'] = str(exc)
    finally:
        with lock:
            state['training'] = False


@app.post('/api/train', status_code=202)
def start_training(request: TrainingRequest):
    path = data_path(request.filename)
    if not path.exists():
        raise HTTPException(404, 'CSV not found. Upload it first.')
    with lock:
        if state['training']:
            raise HTTPException(409, 'Training is already running.')
        state['training'] = True
        state['error'] = None
    threading.Thread(target=run_training, args=(path, request), daemon=True).start()
    return {'message': 'Training started. Model selection uses validation data; final scores use later, unseen data.'}


def get_dashboard(horizon):
    result = state['result']
    if result is None:
        raise HTTPException(409, 'No trained model yet. Import data and train first.')
    return dashboard(result, horizon)


@app.get('/api/dashboard')
def get_forecast(horizon: int = 1):
    if horizon not in (1, 6, 12, 24):
        raise HTTPException(422, 'Choose a 1, 6, 12 or 24 hour horizon.')
    return get_dashboard(horizon)


@app.post('/api/allocate')
def allocation(request: AllocationRequest):
    data = get_dashboard(request.horizon)
    try:
        return allocate(data['zones'], request.supply, request.priorities, request.demand_multipliers)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/analysis')
def analysis():
    result = state['result']
    if not result or 'analysis' not in result:
        raise HTTPException(409, 'Train the model to generate detailed evaluation evidence.')
    return result['analysis']


@app.post('/api/map-timeline')
def map_timeline(request: MapTimelineRequest):
    result = state['result']
    if result is None:
        raise HTTPException(409, 'Train a model before playing the forecast scenario.')
    frames = []
    try:
        for hour in range(24):
            zones = [{**zone, 'predicted_demand': result['forecast_by_zone'][zone['id']][hour]['predicted']}
                     for zone in result['zones']]
            timestamp = result['forecast_by_zone'][zones[0]['id']][hour]['timestamp']
            frames.append(dict(timestamp=timestamp, allocation=allocate(zones, request.hourly_supply, request.priorities)))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return dict(unit=result['source']['unit'], timezone=result['source']['timezone'],
                forecast_origin=result['forecast_origin'], frames=frames,
                note='Forecast scenario playback, not live sensors. A constant available volume is supplied each hour. Unused water does not carry into later hours; reservoir storage and pipe constraints are not modeled. Colors show demand coverage, not probabilities.')


@app.get('/api/zone-series')
def zone_series(zone_id: str, horizon: int = 1):
    if horizon not in (1, 6, 12, 24):
        raise HTTPException(422, 'Choose a 1, 6, 12 or 24 hour horizon.')
    result = state['result']
    if not result or 'zone_history' not in result:
        raise HTTPException(409, 'Train the model to generate district histories.')
    zone = next((z for z in result['zones'] if z['id'] == zone_id), None)
    if zone is None:
        raise HTTPException(404, 'District not found.')
    return dict(id=zone_id, name=zone['name'], history=result['zone_history'][zone_id],
                forecast=result['forecast_by_zone'][zone_id][:horizon],
                unit=result['source']['unit'], timezone=result['source']['timezone'])


DIST = ROOT / 'frontend' / 'dist'


@app.get('/{page}', include_in_schema=False)
def frontend_page(page: str):
    if page in {'dashboard', 'forecasts', 'anomalies', 'allocation', 'zones', 'analysis', 'data', 'map', 'welcome', 'location'} and (DIST / 'index.html').exists():
        return FileResponse(DIST / 'index.html')
    raise HTTPException(404, 'Page not found.')


if DIST.exists():
    app.mount('/', StaticFiles(directory=DIST, html=True), name='frontend')


