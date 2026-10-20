import pytest
from smart_water.data import demo,ValidationError
from smart_water.uploads import import_csvs
from smart_water.forecast import train,predict


def csv(frame):return frame.to_csv(index=False).encode()


def test_consumption_only_and_full_input():
    data=demo()
    imported=import_csvs(csv(data.history))
    assert imported.supply.empty and imported.connections.empty and imported.weather.empty
    assert (imported.zones.priority_weight==1).all()
    complete=import_csvs(csv(data.history),csv(data.supply),csv(data.zones),csv(data.connections),csv(data.weather))
    assert not complete.weather.empty and len(complete.supply)==len(data.supply)


def test_embedded_weather_affects_demand():
    data=demo()
    joined=data.history.merge(data.weather,on='timestamp')
    imported=import_csvs(csv(joined))
    bundle=train(imported)
    baseline=predict(bundle,imported)
    hotter=predict(bundle,imported,temperature_shift=8)
    assert (baseline.predicted_demand-hotter.predicted_demand).abs().sum()>1
    naive=predict(bundle,imported,kind='Seasonal naive')
    changed_naive=predict(bundle,imported,kind='Seasonal naive',temperature_shift=8)
    assert naive.equals(changed_naive)


def test_conflicting_weather_and_bad_csv():
    data=demo();joined=data.history.merge(data.weather,on='timestamp')
    joined.loc[0,'temperature']+=10
    with pytest.raises(ValidationError,match='agree'):import_csvs(csv(joined))
    with pytest.raises(ValidationError):import_csvs(b'not a consumption CSV')
