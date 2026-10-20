"""Run from project root: python -m scripts.train --help"""
import argparse
from pathlib import Path
from backend.forecasting import train

parser = argparse.ArgumentParser(description='Train and evaluate Requiem on an hourly consumption CSV.')
parser.add_argument('csv')
parser.add_argument('--timestamp', required=True)
parser.add_argument('--target', required=True)
parser.add_argument('--zone', default=None)
parser.add_argument('--unit', default='dataset units')
args = parser.parse_args()
result = train(args.csv, args.timestamp, args.target, args.zone, args.unit, Path('artifacts'))
print('Selected:', result['metrics']['model'])
print('Test MAE:', result['metrics']['selected_mae'], result['source']['unit'])
print('Weekly baseline MAE:', result['metrics']['baseline_mae'])
print('Artifacts saved to artifacts/. Restart the app to load them.')
