import numpy as np
import pandas as pd
import pytest
from smart_water.data import demo,validate,cumulative_to_intervals,ValidationError
from smart_water.forecast import MODELS,train,predict,save,load,recursive,features,wide_history
from smart_water.allocation import shortage_plan,allocate

@pytest.fixture(scope='module')
def data():
    return demo()

@pytest.fixture(scope='module')
def bundle(data):
    return train(data)


def revalidate(data,**changes):
    args=dict(history=data.history,supply=data.supply,zones=data.zones,connections=data.connections,weather=data.weather,frequency=data.frequency)
    args.update(changes)
    return validate(**args)

@pytest.mark.parametrize('bad',['negative','missing','duplicate','gap','timestamp','unknown','infinite'])
def test_bad_history(data,bad):
    history=data.history.copy()
    if bad=='negative': history.loc[0,'consumption_m3']=-1
    if bad=='missing': history.loc[0,'consumption_m3']=np.nan
    if bad=='duplicate': history=pd.concat([history,history.iloc[:1]])
    if bad=='gap': history=history.iloc[1:]
    if bad=='timestamp': history['timestamp']=history.timestamp.astype(str); history.loc[0,'timestamp']='invalid'
    if bad=='unknown': history.loc[0,'zone_id']='UNKNOWN'
    if bad=='infinite': history.loc[0,'consumption_m3']=np.inf
    with pytest.raises(ValidationError): revalidate(data,history=history)


def test_zero_is_observation(data):
    history=data.history.copy(); history.loc[0,'consumption_m3']=0
    assert revalidate(data,history=history).history.consumption_m3.iloc[0]==0


def test_cumulative_resets_and_first_reading():
    meter=pd.DataFrame({'timestamp':pd.date_range('2026-01-01',periods=3,freq='h'),'zone_id':['A']*3,'meter_m3':[100,105,105]})
    assert cumulative_to_intervals(meter).consumption_m3.tolist()==[5,0]
    meter.loc[2,'meter_m3']=2
    with pytest.raises(ValidationError,match='Meter reset'): cumulative_to_intervals(meter)


def test_incomplete_supply(data,bundle):
    forecast=predict(bundle,data)
    with pytest.raises(ValidationError,match='cover'): shortage_plan(forecast,data.supply.iloc[5:],data.zones)


def test_splits_calibration_and_roundtrip(data,bundle,tmp_path):
    evaluation=bundle['evaluation']
    assert (evaluation.origin<evaluation.timestamp).all()
    validation=evaluation.query('split == "Validation"')
    test=evaluation.query('split == "Test"')
    assert validation.timestamp.max()<test.timestamp.min()
    assert not evaluation.duplicated(['timestamp','zone_id','model','split']).any()
    for (model,zone),g in validation.groupby(['model','zone_id']):
        assert bundle['calibration'][(model,zone)]['band']==pytest.approx(np.quantile(g.residual.abs(),.9))
    save(bundle,tmp_path)
    restored=load(data,tmp_path)
    pd.testing.assert_frame_equal(predict(bundle,data),predict(restored,data))
    assert set(bundle['alerts'].severity)<= {'Medium','High'}
    assert (bundle['alerts'].residual>0).any() and (bundle['alerts'].residual<0).any()


def test_each_forecast_model_is_evaluated_and_predicts(data,bundle):
    assert set(bundle['metrics'].model) == set(MODELS)
    assert set(bundle['models']) == {'Random forest', 'Extra trees', 'Neural network'}
    assert not bundle['epoch_log'].empty
    assert bundle['epoch_log'].epoch.min() == 1
    for kind in MODELS:
        forecast = predict(bundle, data, horizon=3, kind=kind)
        assert len(forecast) == 3 * len(data.zones)


def test_future_weather_cannot_leak(data,bundle):
    wide=wide_history(data).iloc[:1000]
    dates=pd.date_range(wide.index[-1]+pd.Timedelta(hours=1),periods=48,freq='h')
    weather=data.weather.set_index('timestamp')
    changed=weather.copy(); changed.loc[changed.index>wide.index[-1],['temperature','rainfall']]=100000
    a=recursive(bundle['model'],wide,dates,24,'Random forest',weather)
    b=recursive(bundle['model'],wide,dates,24,'Random forest',changed)
    np.testing.assert_array_equal(a,b)


def test_recursive_uses_predictions():
    class LastPlusOne:
        def __init__(self): self.seen=[]
        def predict(self,x):
            self.seen.append(x.copy())
            return x[:,7]+1 # 6 calendar + 1 zone one-hot, then lag 1
    wide=pd.DataFrame({'A':np.ones(168)},index=pd.date_range('2026-01-01',periods=168,freq='h',tz='UTC'))
    model=LastPlusOne()
    dates=pd.date_range(wide.index[-1]+pd.Timedelta(hours=1),periods=3,freq='h')
    values=recursive(model,wide,dates,24,'Random forest')
    np.testing.assert_array_equal(values[:,0],[2,3,4])


def simple_plan(supply,demand,priority=None):
    ids=list(supply)
    t=pd.Timestamp('2026-01-01',tz='UTC')
    forecast=pd.DataFrame({'timestamp':t,'zone_id':ids,'predicted_demand':[demand[z] for z in ids],
                           'lower_m3':[demand[z] for z in ids],'upper_m3':[demand[z]+5 for z in ids]})
    schedule=pd.DataFrame({'timestamp':t,'zone_id':ids,'available_supply_m3':[supply[z] for z in ids]})
    zones=pd.DataFrame({'zone_id':ids,'zone_name':ids,'priority_weight':[priority.get(z,1) if priority else 1 for z in ids]})
    return shortage_plan(forecast,schedule,zones)


def edges(rows):
    return pd.DataFrame(rows,columns=['source_zone','destination_zone','capacity_m3','transfer_cost'])

@pytest.mark.parametrize('method',['Optimization','Priority baseline'])
def test_capacity_and_conservation(method):
    plan=simple_plan({'A':100,'B':0,'C':0},{'A':50,'B':30,'C':50})
    result,transfers=allocate(plan,edges([('A','B',20,0),('A','C',20,0)]),method)
    assert transfers.volume_m3.sum()==pytest.approx(40)
    assert result.remaining_shortage_m3.sum()==pytest.approx(40)
    assert result.supply_after_m3.sum()==pytest.approx(result.available_supply_m3.sum())
    assert (result.sent_m3<=result.surplus_m3+1e-6).all()
    assert (result.received_m3<=result.shortage_m3+1e-6).all()


def test_no_multihop_and_disconnected():
    plan=simple_plan({'A':100,'B':10,'C':0},{'A':50,'B':10,'C':50})
    result,transfers=allocate(plan,edges([('A','B',100,0),('B','C',100,0)]))
    assert transfers.empty
    assert result.remaining_shortage_m3.sum()==50


def test_priority_precedes_cost():
    plan=simple_plan({'A':10,'B':0,'C':0},{'A':0,'B':10,'C':10},{'B':2,'C':1})
    result,transfers=allocate(plan,edges([('A','B',10,1e9),('A','C',10,0)]))
    assert transfers.destination_zone.tolist()==['B']
    assert np.isfinite(result.shortage_pct).all()


def test_cost_tiebreak():
    plan=simple_plan({'A':10,'B':10,'C':0},{'A':0,'B':0,'C':10})
    _,transfers=allocate(plan,edges([('A','C',10,5),('B','C',10,1)]))
    assert transfers.source_zone.tolist()==['B']

@pytest.mark.parametrize('method',['Optimization','Priority baseline'])
def test_random_network_invariants(method):
    rng=np.random.default_rng(8)
    for _ in range(12):
        ids=list('ABCDE')
        supply=dict(zip(ids,rng.uniform(0,100,5)))
        demand=dict(zip(ids,rng.uniform(0,100,5)))
        plan=simple_plan(supply,demand)
        network=edges([(s,d,float(rng.uniform(0,30)),float(rng.uniform(0,5))) for s in ids for d in ids if s!=d and rng.random()<.5])
        result,transfers=allocate(plan,network,method)
        assert result.remaining_shortage_m3.sum()<=result.shortage_m3.sum()+1e-6
        assert result.supply_after_m3.min()>=-1e-6
        assert result.supply_after_m3.sum()==pytest.approx(sum(supply.values()))
        for row in transfers.itertuples():
            cap=network.query('source_zone == @row.source_zone and destination_zone == @row.destination_zone').capacity_m3.iloc[0]
            assert 0<=row.volume_m3<=cap+1e-6


def test_daily_resolution():
    original=demo()
    history=original.history.set_index('timestamp').groupby('zone_id').resample('D').consumption_m3.sum().reset_index()
    supply=original.supply.set_index('timestamp').groupby('zone_id').resample('D').available_supply_m3.sum().reset_index()
    data=validate(history,supply,original.zones,original.connections,frequency='D')
    bundle=train(data)
    forecast=predict(bundle,data,3)
    assert len(forecast)==15
    assert (forecast.query('zone_id == "C"').timestamp.diff().dropna()==pd.Timedelta(days=1)).all()

@pytest.mark.parametrize('method',['Optimization','Priority baseline'])
@pytest.mark.parametrize('supply,demand',[
    ({'A':5,'B':0,'C':0},{'A':0,'B':20,'C':10}),
    ({'A':5,'B':0,'C':10},{'A':0,'B':20,'C':20}),
])
def test_demand_and_risk_prioritize_scarce_transfers(method,supply,demand):
    plan=simple_plan(supply,demand)
    _,transfers=allocate(plan,edges([('A','B',5,10),('A','C',5,0)]),method)
    assert transfers.destination_zone.tolist()==['B']
    assert transfers.volume_m3.sum()==pytest.approx(5)
