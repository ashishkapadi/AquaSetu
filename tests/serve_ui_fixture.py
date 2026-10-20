"""Isolated browser QA on port 8001; never populates the real app's data/artifacts."""
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import uvicorn
from backend import main
from backend.forecasting import train


def run():
    with tempfile.TemporaryDirectory(prefix='requiem-ui-test-') as folder:
        work = Path(folder)
        n = 1008
        values = 120 + 30*np.sin(2*np.pi*np.arange(n)/24) + np.random.default_rng(12).normal(0,3,n)
        values[-1] = 220  # Explicit software-test fixture for an unusual-consumption alert.
        frame = pd.DataFrame({'timestamp': pd.date_range('2024-01-01', periods=n, freq='h'), 'consumption': values})
        path = work / 'ARTIFICIAL-QA-FIXTURE-NOT-KAGGLE.csv'
        frame.to_csv(path, index=False)
        main.DATA = work
        main.ARTIFACTS = work / 'artifacts'
        result = train(path, 'timestamp', 'consumption', None, 'test units', main.ARTIFACTS)
        result['source']['url'] = ''
        result['source']['notes'].insert(0, 'Artificial software-test data only. These are not Kaggle results.')
        main.state.update(result=result, error=None, training=False)
        uvicorn.run(main.app, host='127.0.0.1', port=8001)


if __name__ == '__main__':
    run()
