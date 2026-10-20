# Reference inspection and attribution

Reviewed on 2026-10-11 before implementation. All application code was written independently; no source code, model artifacts or datasets were copied into this project. References are architectural background, not claims that another repository solves the integrated redistribution problem.

## HydroAI

Repository: https://github.com/Naifcx47350/HydroAI

Inspected README, `data_pipeline/forecasting.py`, `data_pipeline/anomaly_detection.py`, `gui_streamlit.py`, and LICENSE via GitHub and raw source.

- The forecasting module aggregates hourly flow into daily usage and trains an LSTM with train-fitted MinMax scaling and an optional log transform.
- Anomaly detection is an LSTM autoencoder using reconstruction errors; the Streamlit GUI exposes separate demo workflows.
- These informed modular forecasting/anomaly/UI separation. This project uses Random Forest and origin-stamped residual alerts instead, with validation-only thresholds.
- MIT license, copyright 2025 Naif AlSahabi. No code reused.

## water-forecast

Repository: https://github.com/aildnont/water-forecast

Inspected README, `src/data/preprocess.py`, `src/models/skmodels.py`, `src/train.py`, and LICENSE.

- Documents daily aggregate demand modelling for the City of London; it is not evidence of hourly zone data.
- Source includes sklearn model wrappers, training-data scaling, joblib serialization, recursive forecast feedback, chronological splits and time-series model comparison/cross-validation.
- These informed explicit recursive forecasting, baseline comparisons and saved artifacts. No model wrapper or preprocessing implementation was reused.
- MIT license. No code reused.

## wf4bwdf

Repository: https://github.com/WaterFutures/wf4bwdf

The initial browser fetch failed, but GitHub API/raw source access succeeded. Inspected README, `src/wf4bwdf/_data_loading.py`, `src/wf4bwdf/_solution_evaluation.py`, and LICENSE.

- Provides competition DMA inflow/weather/calendar loading and forecast evaluation. It is not an integrated transfer optimizer.
- Loading source declares inflow units in L/s; those must not be interpreted as interval m³. For an interval-average flow, volume is `L/s × interval_seconds / 1000`.
- Iteration loading masks future evaluation inflows; evaluation distinguishes first-day and subsequent-day errors. This informed strict time boundaries and per-zone evaluation.
- MIT code license, copyright 2025 ERC Synergy Grant Water Futures. README identifies the underlying published data as CC BY 4.0. Neither code nor data is redistributed here.

## Kaggle dm1718

Suggested page: https://www.kaggle.com/competitions/dm1718

The page returned no readable schema in the available browsing interface. No dataset file was accessed, no schema was verified, and no Kaggle data was used. This project does not assume that this competition provides zones, weather, hourly readings or supply schedules. To use it later, first inspect downloaded files and their units/resolution and licensing terms, then explicitly transform them into the documented CSV contracts. Do not fabricate unavailable supply or connections without labelling them as scenarios.

## WNTR

Optional reference: https://github.com/USEPA/WNTR

Not integrated and not source-inspected in this implementation. Core operation does not depend on WNTR. No hydraulic feasibility claims are made. A future integration needs a suitable network model, boundary conditions and validated simulation setup.
