"""Train the prepared synthetic CSV bundle and export reproducible results."""
from pathlib import Path
import json
from smart_water.uploads import import_csvs
from smart_water.forecast import train, save, predict
from smart_water.allocation import shortage_plan, allocate

ROOT = Path(__file__).resolve().parent


def main():
    folder = ROOT / 'outputs/demo_csv_bundle'
    read = lambda name: (folder / (name + '.csv')).read_bytes()
    data = import_csvs(read('consumption_with_weather'), read('supply'),
                       read('zones'), read('connections'))
    data.synthetic = True
    bundle = train(data)
    save(bundle, ROOT / 'artifacts')
    output = ROOT / 'outputs/demo_training_results'
    output.mkdir(parents=True, exist_ok=True)
    validation = bundle['metrics'].query("split == 'Validation' and zone_id == 'ALL'")
    chosen = validation.sort_values('MAE_m3').iloc[0]['model']
    forecast = predict(bundle, data, 72, chosen)
    plan, transfers = allocate(shortage_plan(forecast, data.supply, data.zones), data.connections)
    reduced_supply = data.supply.copy()
    reduced_supply['available_supply_m3'] *= .8
    reduced, reduced_transfers = allocate(shortage_plan(forecast, reduced_supply, data.zones), data.connections)
    for name, frame in [('forecast_72_hours', forecast), ('model_metrics', bundle['metrics']),
                        ('neural_network_epochs', bundle['epoch_log']),
                        ('historical_evaluation', bundle['evaluation']), ('anomaly_alerts', bundle['alerts']),
                        ('water_balance', plan), ('transfers', transfers),
                        ('water_balance_supply_80pct', reduced), ('transfers_supply_80pct', reduced_transfers)]:
        frame.to_csv(output / (name + '.csv'), index=False)
    report = {'dataset': 'Synthetic demo CSV bundle — not municipal observations',
              'selected_model_by_validation_MAE': chosen,
              'test_metrics': bundle['metrics'].query("split == 'Test' and zone_id == 'ALL'").to_dict('records'),
              'forecast_start_UTC': str(forecast.timestamp.min()), 'forecast_end_UTC': str(forecast.timestamp.max()),
              'forecast_demand_m3': float(forecast.predicted_demand.sum()),
              'shortage_before_m3': float(plan.shortage_m3.sum()),
              'shortage_after_m3': float(plan.remaining_shortage_m3.sum()),
              'redistributed_m3': float(transfers.volume_m3.sum()),
              'model_file': str(ROOT / 'artifacts' / (data.fingerprint + '.joblib')),
              'training_metadata': bundle['metadata']}
    (output / 'training_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
