SYNTHETIC DEMO TRAINING RESULTS
Random forest selected using validation MAE, then evaluated against Seasonal naive on held-out chronological test windows. Final model refit on all 90 days.
Forecasts span September 29 to October 1, 2026 UTC, immediately after dataset history, not after the current date.
MAE/RMSE units: cubic metres per zone-hour. Band coverage is empirical, not an accuracy guarantee.
Weather is a past-only climatology scenario, not live weather forecasts.
Supply_80pct files illustrate reduced supply using the same forecast.
Anomaly CSV contains historical backtests for both models; filter by model before counting.
Reproduce with .venv/bin/python train_demo.py from the project folder.
