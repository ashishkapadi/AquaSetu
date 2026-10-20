# Requiem — Smart Water Redistribution

A local ML hackathon application that forecasts hourly water consumption, flags unusual consumption and recommends allocation of a shared water supply.

**Ready with real data:** the app is trained on the open Water-Futures / Battle of Water Demand Forecasting (BWDF) dataset: 19,679 hourly timestamps across 10 measured districts. The user approved this alternative after Kaggle required competition-rule acceptance. No simulated zones are used in the current trained app.

Next-hour test MAE is **3.0952 m³ per district-hour**, compared with **4.3201 m³** for the weekly baseline: **28.35% lower error**. The test period runs from 28 November 2022 at 22:00 UTC through 31 March 2023 at 21:00 UTC, with 29,081 scored district-hour observations. These are our own chronological-holdout results, not original competition leaderboard scores.

## Start on this Windows machine

From `D:\Ashish\projects\Requiem`:

```powershell
.\start.ps1
```

Open http://127.0.0.1:8000. The launch script builds the frontend if its build is missing. To rebuild after UI edits, run `npm.cmd run build` from `frontend`, then restart the server.

For a fresh installation, install Python 3.12+ and Node.js, then:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
.\start.ps1
```

If using uv, `uv venv --python 3.12 .venv` and `uv pip install --python .venv\Scripts\python.exe -r requirements.txt` are equivalent setup steps.

## Reproduce the current dataset and model

The source files and implementation are published by Water-Futures:
https://github.com/WaterFutures/wf4bwdf

Dataset attribution: Alvisi et al. (2025), *Battle of Water Demand Forecasting*, DOI `10.1061/JWRMD5.WRENG-6887`. Data are distributed under CC BY 4.0. The original files are retained in `data/waterfutures-original/`; the conversion records source URLs and SHA-256 hashes in `data/waterfutures_hourly.metadata.json`.

```powershell
.\.venv\Scripts\python.exe scripts\prepare_waterfutures.py
.\.venv\Scripts\python.exe -m scripts.train data\waterfutures_hourly.csv --timestamp timestamp --target consumption_m3 --zone zone --unit "m³"
.\start.ps1
```

The converter preserves missing measurements, localizes CET/CEST timestamps to Europe/Rome, converts them to UTC, and converts hourly mean flows from L/s to hourly volume in m³ using `flow × 3.6`. District inflow is a demand proxy and can include network losses. The 10 published districts include hospital, residential, mixed-use and industrial service areas. No location in India or physical network topology is claimed.

The raw table has 196,790 district-hour rows and 10,171 missing measurements. Missing targets are excluded from model scoring. Weather data are downloaded for traceability but are not used as model inputs in this version.

When retraining in the UI, select `waterfutures_hourly.csv`, `timestamp`, `consumption_m3`, `zone`, and units `m³`. The prepared dataset's source metadata and unit are retained automatically. A complete retraining run takes seconds on this machine after dependencies have loaded.

## Optional: original Kaggle dataset

Source: https://www.kaggle.com/competitions/dm1718

1. Sign in to Kaggle and open the competition's Data tab. Complete any required access steps yourself.
2. Download and extract the files into `data/kaggle-original/`.
3. Inspect the training file and competition description before choosing the consumption, timestamp and optional zone columns. Do not use a sample submission as training history or invent dates for sample IDs.
4. Upload the correct hourly history CSV through the dashboard. Select its columns and declare the documented unit. Use `dataset units` until the physical unit is verified.

The programmatic alternative uses the user's snippet:

```powershell
.\.venv\Scripts\python.exe -c "import kagglehub; kagglehub.login()"
.\.venv\Scripts\python.exe scripts\download_data.py
```

Enter the API token in the local login prompt, never in source code. The download script preserves the original files. See Kaggle's official authentication instructions: https://github.com/Kaggle/kagglehub#authenticate

The Kaggle file structure was not inspected because access remained restricted. The working demo uses the approved BWDF alternative. To use Kaggle later, inspect its actual schema before mapping or converting it.

## CSV requirements

- An actual date/hour column, e.g. `2024-01-01 00:00:00`; nonnumeric, hour-aligned, consistent timezone.
- Nonnegative water **volume consumed within each hour**. Convert rates or cumulative counters using documented units before import.
- At least 672 observed readings (28 days) per zone, with no duplicate timestamp/zone pairs.
- At most 15% missing hours; zone histories must have the same start and end.
- Optional zone labels; otherwise the real aggregate series is split into five explicitly simulated allocation zones.
- No geographic coordinates or weather measurements are invented.

## What the model does

1. Sort the series by time. Use the first 70% for initial training, the next 15% for model selection and the last 15% for final evaluation.
2. Build lag features from 1, 2, 3, 24, 48 and 168 hours earlier; rolling means from past 6, 24 and 168 hours; and hour/weekday/month features.
3. Fit a compact gradient-boosted tree regressor and compare its validation MAE with a same-hour-last-week baseline.
4. Select the lower validation-MAE method. Refit the ML candidate on training plus validation observations, then score both methods on the final test period. Test predictions may use actual readings from earlier test hours: this is a next-hour rolling-origin evaluation, not a fixed-origin 24-hour test.
5. Refit on all available history for the next forecast. Future 6/12/24-hour predictions recursively use previous predictions. Their accuracy is not represented by the next-hour MAE.
6. Separately evaluate 1/6/12/24-hour rollouts using pre-test models at up to eight predetermined weekly origins spread across the test period. Use identical eligible origins across all districts and horizons; exclude missing targets and unresolved history. Report hourly error and total-horizon district-volume error. The current source yields five eligible origins, so this evidence is limited.

Dedicated pages: Overview (`/`), Forecasts (`/forecasts`), Anomalies (`/anomalies`), Allocation (`/allocation`), Zones (`/zones`), Model Analysis (`/analysis`), and Data (`/data`). Direct browser refresh is supported. Detailed evaluation is available at `/api/analysis`; individual district plots use `/api/zone-series`.

Area Map (`/map`) adds interactive illustrative district polygons, coverage colors, shared scenario controls, and 24-hour forecast playback. `POST /api/map-timeline` accepts `hourly_supply` and optional `priorities`, returning 24 hourly allocations using the existing saved forecasts. Playback assumes constant hourly supply, no storage carryover, and no pipe constraints. No live telemetry or verified district geography is claimed.

References: [Shadcn Admin](https://github.com/satnaing/shadcn-admin) informed sidebar and focused-page organization. [WaterFutures evaluation](https://github.com/WaterFutures/wf4bwdf/blob/main/src/wf4bwdf/_solution_evaluation.py) informed district/horizon reporting. Our model, split, metrics and interface implementation are independent; no competition score is claimed.

Missing inputs may be forward-filled for at most six hours using older readings only. Missing actual targets are excluded from training and evaluation. Long gaps fail validation if they prevent forecasting.

## Unusual consumption and allocation

An alert compares the latest observed consumption with its prediction. Its threshold is the 99th percentile of absolute validation errors, with a small positive floor. It signals an unusual reading; it does not diagnose a leak. With simulated zones, the alert is an inherited system-level signal, not evidence about individual neighborhoods.

The recent-alert history shows up to 20 unusual readings from the last 72 hours, computed using predictions made by models trained before the final test period. The current real dataset has 10 such readings and no latest-hour alert.

For forecast demand `d_i`, priority `w_i` and shared supply `S`, allocation is:

`a_i = min(d_i, lambda * w_i * d_i)`

The algorithm finds a scale `lambda` so allocations total `min(S, sum(d_i))`. Equal weights give equal demand coverage. Higher weights get greater coverage until demand is met. The result reports shortages and excess supply. Demand and supply refer to the same selected horizon.

Shortage-risk labels describe coverage under that scenario: high below 75%, medium from 75% to below 95%, low at 95% or above. They are decision thresholds, not learned probabilities.

This is a planning simulation. Physical pipe connections, pressure, storage, travel time, minimum service requirements and transfer capacity are not modeled. No recommendation actuates infrastructure.

## Reproduce training from the terminal

```powershell
.\.venv\Scripts\python.exe -m scripts.train data\history.csv --timestamp timestamp --target consumption --unit "documented units"
```

Add `--zone zone` only when the file contains genuine zone labels. Restart the app after terminal training. Models, forecast data and the training report are saved in `artifacts/`; those generated files are ignored by Git.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
```

Tests check temporal feature isolation, CSV validation, a complete training/persistence pass, API input handling and conservation across randomized allocation scenarios. Test fixture accuracy is not a result for the Kaggle dataset.

## Project structure

- `backend/data.py`: CSV validation and hourly series.
- `backend/forecasting.py`: features, training, selection, evaluation and future forecasts.
- `backend/allocation.py`: constrained allocation calculation.
- `backend/main.py`: upload, training, forecast and allocation API.
- `frontend/`: React dashboard.
- `JUDGE_GUIDE.md`: explanation and demonstration script.
- `CONTRACT.md`: frontend/backend contract.
