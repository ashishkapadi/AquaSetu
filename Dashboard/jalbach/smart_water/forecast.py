"""Past-only features and recursive, origin-stamped forecasts."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import platform
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

VERSION = 3
MODELS = ['Random forest', 'Extra trees', 'Neural network', 'Seasonal naive']


def wide_history(data):
    return data.history.pivot(index='timestamp', columns='zone_id', values='consumption_m3').sort_index(axis=1)


def features(timestamp, past, day, weather=None):
    """Each row is one zone; past ends strictly before timestamp."""
    z = past.shape[1]
    calendar = [np.sin(2*np.pi*timestamp.hour/24), np.cos(2*np.pi*timestamp.hour/24),
                timestamp.dayofweek, int(timestamp.dayofweek>=5), timestamp.month,
                (timestamp.month%12)//3]
    cols = [np.tile(calendar,(z,1)), np.eye(z), past[-1,:,None],past[-day,:,None],past[-7*day,:,None],
            past[-day:].mean(axis=0)[:,None],past[-day:].std(axis=0)[:,None],
            past[-7*day:].mean(axis=0)[:,None]]
    if weather is not None:
        cols.append(np.tile(weather,(z,1)))
    return np.hstack(cols)


def fit_model(wide, weather, day, kind='Random forest'):
    if kind == 'Random forest':
        estimator = RandomForestRegressor
    elif kind == 'Extra trees':
        estimator = ExtraTreesRegressor
    elif kind == 'Neural network':
        estimator = None
    else:
        raise ValueError('Only trained tree models can be fitted.')
    values = wide.to_numpy()
    x,y = [],[]
    for i in range(7*day,len(wide)):
        w = weather.loc[wide.index[i],['temperature','rainfall']].to_numpy(dtype=float) if weather is not None else None
        x.append(features(wide.index[i],values[:i],day,w))
        y.append(values[i])
    if kind == 'Neural network':
        # The scaler keeps demand, calendar and weather features comparable for
        # gradient-based learning. max_iter is the epoch cap; early stopping
        # restores the best validation epoch when progress plateaus.
        model = Pipeline([('scale', StandardScaler()), ('network', MLPRegressor(
            hidden_layer_sizes=(64, 32), activation='relu', alpha=1e-3,
            batch_size=128, learning_rate_init=1e-3, max_iter=80,
            early_stopping=True, validation_fraction=.15, n_iter_no_change=10,
            random_state=42))])
    else:
        model = estimator(n_estimators=64, max_depth=14, min_samples_leaf=4, random_state=42, n_jobs=1)
    model.fit(np.vstack(x),np.concatenate(y))
    return model


def fit_models(wide, weather, day):
    return {kind: fit_model(wide, weather, day, kind) for kind in MODELS if kind != 'Seasonal naive'}


def epoch_log(models, stage):
    """Return neural-network loss after every completed epoch for audit/export."""
    network = models.get('Neural network')
    if network is None:
        return pd.DataFrame(columns=['training_stage', 'epoch', 'loss'])
    losses = network.named_steps['network'].loss_curve_
    return pd.DataFrame({'training_stage': stage, 'epoch': np.arange(1, len(losses)+1), 'loss': losses})


def weather_scenario(weather, dates, origin, temperature_shift=0., rainfall_shift=0.):
    if weather is None:
        return None
    known = weather.loc[weather.index <= origin].tail(24*7)
    # Calendar-hour climatology calculated from information available at the origin.
    means = known.groupby(known.index.hour)[['temperature','rainfall']].mean()
    result = np.array([means.loc[t.hour].to_numpy() if t.hour in means.index else known[['temperature','rainfall']].mean().to_numpy() for t in dates])
    result[:,0] += temperature_shift
    result[:,1] = np.maximum(0,result[:,1]+rainfall_shift)
    return result


def recursive(model, wide, dates, day, kind, weather=None, temperature_shift=0., rainfall_shift=0.):
    past = wide.to_numpy().copy()
    scenario = weather_scenario(weather,dates,wide.index[-1],temperature_shift,rainfall_shift)
    forecasts = []
    for i,timestamp in enumerate(dates):
        if kind == 'Seasonal naive':
            prediction = past[-7*day].copy()
        else:
            w = scenario[i] if scenario is not None else None
            prediction = np.maximum(0,model.predict(features(timestamp,past,day,w)))
        forecasts.append(prediction)
        past = np.vstack([past,prediction])
    return np.array(forecasts)


def backtest(models, wide, weather, day, start, end, horizon, split):
    # Three disjoint rolling origins per split; model frozen within a split.
    origins = np.unique(np.linspace(start,end-horizon,3,dtype=int))
    frames = []
    for origin in origins:
        dates = wide.index[origin:origin+horizon]
        for kind in MODELS:
            predictions = recursive(models.get(kind),wide.iloc[:origin],dates,day,kind,weather)
            for j,zone in enumerate(wide.columns):
                frames.append(pd.DataFrame({'timestamp':dates,'zone_id':zone,'model':kind,'split':split,
                    'origin':wide.index[origin-1], 'lead':np.arange(1,len(dates)+1),
                    'actual':wide.iloc[origin:origin+horizon,j].to_numpy(),'expected':predictions[:,j]}))
    result = pd.concat(frames,ignore_index=True)
    result['residual'] = result.actual-result.expected
    return result


def metrics_for(evaluation):
    rows=[]
    for (split,model),part in evaluation.groupby(['split','model']):
        groups=[('ALL',part)]+list(part.groupby('zone_id'))
        for zone,g in groups:
            rows.append({'split':split,'model':model,'zone_id':zone,'MAE_m3':g.residual.abs().mean(),
                         'RMSE_m3':np.sqrt(np.mean(g.residual**2)), 'samples':len(g),
                         'band_coverage':g.covered.mean()})
    return pd.DataFrame(rows)


def train(data):
    wide = wide_history(data)
    weather = data.weather.set_index('timestamp') if not data.weather.empty else None
    day = 24 if data.frequency=='h' else 1
    horizon = 72 if day==24 else 7
    n=len(wide)
    a,b=int(n*.6),int(n*.8)
    # Need three non-overlapping horizon blocks for each evaluation split.
    horizon = min(horizon,(b-a)//3,(n-b)//3)
    validation_models = fit_models(wide.iloc[:a],weather,day)
    validation = backtest(validation_models,wide,weather,day,a,b,horizon,'Validation')
    epochs = [epoch_log(validation_models, 'Validation training')]
    calibration = {}
    for (kind,zone),g in validation.groupby(['model','zone_id']):
        calibration[(kind,zone)] = {'band':float(np.quantile(g.residual.abs(),.90)),
                                   'alert':float(max(np.quantile(g.residual.abs(),.99),1e-6)),
                                   'samples':len(g)}
    test_models = fit_models(wide.iloc[:b],weather,day)
    test = backtest(test_models,wide,weather,day,b,n,horizon,'Test')
    epochs.append(epoch_log(test_models, 'Test training'))
    evaluation = pd.concat([validation,test],ignore_index=True)
    evaluation['band_m3'] = [calibration[(r.model,r.zone_id)]['band'] for r in evaluation.itertuples()]
    evaluation['covered'] = evaluation.residual.abs() <= evaluation.band_m3
    alerts=test.copy()
    alerts['threshold_m3']=[calibration[(r.model,r.zone_id)]['alert'] for r in alerts.itertuples()]
    alerts=alerts[alerts.residual.abs()>alerts.threshold_m3].copy()
    alerts['severity']=np.where(alerts.residual.abs()>2*alerts.threshold_m3,'High','Medium')
    alerts['explanation']=np.where(alerts.residual>0,
        'Unusually high usage: possible demand surge, leakage or sensor issue; investigate.',
        'Unusually low usage: possible interruption, changed activity or sensor issue; investigate.')
    final_models=fit_models(wide,weather,day)
    epochs.append(epoch_log(final_models, 'Final production training'))
    metadata={'version':VERSION,'fingerprint':data.fingerprint,'trained_at':datetime.now(timezone.utc).isoformat(),
              'training_end':str(wide.index[-1]),'frequency':data.frequency,'zones':list(wide.columns),
              'evaluation_horizon':horizon,'initial_train_end':str(wide.index[a-1]),
              'validation_end':str(wide.index[b-1]),'test_end':str(wide.index[-1]),
              'weather':'Past-only hour-of-day climatology scenario' if weather is not None else 'Not supplied',
              'models':MODELS,
              'python':platform.python_version(),'sklearn':sklearn.__version__,
              'notes':'60/20/20 chronological split; three rolling origins per split. Final model refit on all history. '
                      '90% absolute-residual bands and 99% alert thresholds pooled over evaluated leads per zone; '
                      'nominal coverage is not guaranteed under drift. Holidays not supplied or inferred.'}
    # Keep the Random Forest alias for callers using a saved bundle directly.
    return {'model':final_models['Random forest'],'models':final_models,'metadata':metadata,'calibration':calibration,
            'epoch_log':pd.concat(epochs, ignore_index=True),
            'evaluation':evaluation,'metrics':metrics_for(evaluation),'alerts':alerts}


def predict(bundle,data,horizon=24,kind='Random forest',temperature_shift=0.,rainfall_shift=0.):
    if kind not in MODELS:
        raise ValueError('Unknown forecast model.')
    if bundle['metadata']['fingerprint'] != data.fingerprint:
        raise ValueError('History or weather changed. Retrain before forecasting.')
    if not 1 <= horizon <= bundle['metadata']['evaluation_horizon']:
        raise ValueError('Requested horizon exceeds the empirically evaluated horizon; add more history.')
    wide=wide_history(data)
    delta=pd.Timedelta(hours=1) if data.frequency=='h' else pd.Timedelta(days=1)
    dates=pd.date_range(wide.index[-1]+delta,periods=horizon,freq=data.frequency)
    weather=data.weather.set_index('timestamp') if not data.weather.empty else None
    model = None if kind == 'Seasonal naive' else bundle['models'][kind]
    predictions=recursive(model,wide,dates,24 if data.frequency=='h' else 1,kind,weather,temperature_shift,rainfall_shift)
    frames=[]
    for j,zone in enumerate(wide.columns):
        band=bundle['calibration'][(kind,zone)]['band']
        frames.append(pd.DataFrame({'timestamp':dates,'zone_id':zone,'predicted_demand':predictions[:,j],
            'lower_m3':np.maximum(0,predictions[:,j]-band),'upper_m3':predictions[:,j]+band}))
    return pd.concat(frames,ignore_index=True)


def save(bundle,directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    key=bundle['metadata']['fingerprint']
    temp=directory/f'{key}.{os.getpid()}.tmp'
    joblib.dump(bundle,temp,compress=3)
    temp.replace(directory/f'{key}.joblib')
    (directory/f'{key}.json').write_text(json.dumps(bundle['metadata'],indent=2))


def load(data,directory):
    path=Path(directory)/f'{data.fingerprint}.joblib'
    if not path.exists():
        return None
    # Only local artifacts created by this application; never load uploaded pickle/joblib.
    try:
        bundle=joblib.load(path)
        meta=bundle['metadata']
        if meta['version']==VERSION and meta['sklearn']==sklearn.__version__ and meta['fingerprint']==data.fingerprint:
            return bundle
    except (ValueError,KeyError,EOFError):
        pass
    return None
