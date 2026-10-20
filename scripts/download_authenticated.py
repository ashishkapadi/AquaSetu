"""Read a Kaggle token privately for this process only; do not save it."""
import getpass
import os
import runpy
from pathlib import Path

token = getpass.getpass('Kaggle API token (hidden; not saved): ')
os.environ['KAGGLE_API_TOKEN'] = token.strip()
del token
try:
    runpy.run_path(str(Path(__file__).with_name('download_data.py')), run_name='__main__')
finally:
    os.environ.pop('KAGGLE_API_TOKEN', None)
