"""Download the specified competition with the user's configured Kaggle access."""
from pathlib import Path
import shutil
import kagglehub

root = Path(__file__).resolve().parents[1]
destination = root / 'data' / 'kaggle-original'
destination.mkdir(parents=True, exist_ok=True)
source = Path(kagglehub.competition_download('dm1718'))
for file in source.rglob('*'):
    if file.is_file():
        target = destination / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(file, target)
print('Competition files:', destination)
