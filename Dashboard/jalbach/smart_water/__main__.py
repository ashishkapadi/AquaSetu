"""Offline demo training and CSV export: python -m smart_water."""
from pathlib import Path
from .data import demo
from .forecast import train, predict, save
from .allocation import shortage_plan, allocate


def main():
    root=Path(__file__).resolve().parents[1]
    data=demo()
    examples=root/'data'/'examples'
    examples.mkdir(parents=True,exist_ok=True)
    for name,frame in [('consumption',data.history),('supply',data.supply),('zones',data.zones),('connections',data.connections),('weather',data.weather)]:
        frame.to_csv(examples/f'{name}.csv',index=False)
    bundle=train(data)
    save(bundle,root/'artifacts')
    forecast=predict(bundle,data)
    result,transfers=allocate(shortage_plan(forecast,data.supply,data.zones),data.connections)
    for name,frame in [('forecast',forecast),('balance',result),('transfers',transfers),('metrics',bundle['metrics']),('alerts',bundle['alerts'])]:
        frame.to_csv(root/'artifacts'/f'demo_{name}.csv',index=False)
    print(bundle['metrics'].query('split == "Test" and zone_id == "ALL"').to_string(index=False))
    print(f'Synthetic scenario shortage: {result.shortage_m3.sum():.1f} -> {result.remaining_shortage_m3.sum():.1f} m³')
    print('Saved examples, model, metadata and reports.')

if __name__=='__main__':
    main()
