# Source and transformation record

Current source: **Water-Futures implementation of the Battle of Water Demand Forecasting (BWDF)**.

- Repository and dataset documentation: https://github.com/WaterFutures/wf4bwdf
- Dataset paper: Alvisi et al. (2025), *Battle of Water Demand Forecasting*, https://doi.org/10.1061/JWRMD5.WRENG-6887
- License stated by the distributor: Creative Commons Attribution 4.0 for data; MIT for implementation.
- Original files: `data/waterfutures-original/InflowData.xlsx` and `WeatherData.xlsx`.
- Machine-readable download URLs and SHA-256 checksums: `data/waterfutures_hourly.metadata.json`.
- Reproduction: `scripts/prepare_waterfutures.py`.

The inflow workbook has 19,679 hourly timestamps and 10 DMA columns, originally labelled L/s. It covers 1 January 2021 through 31 March 2023 in CET/CEST. UTC-normalized timestamps run from 31 December 2020 at 23:00 to 31 March 2023 at 21:00. All 19,679 normalized hours are unique and contiguous.

The source contains 10,171 missing readings out of 196,790 possible district-hour observations. Missing values remain missing in the prepared CSV. The model may forward-fill features for at most six hours; it never uses an imputed consumption value as a training or evaluation target. Observations are not linearly interpolated using future values.

Hourly volume conversion: `L/s × 3,600 seconds / 1,000 litres per m³ = m³ per hour`. Summing hourly volumes gives the total demand volume for the selected horizon. Available supply in the UI is a volume over that same horizon.

Labels follow the published DMA categories: hospital, rural residential, suburban mixed, near-centre mixed, sports/offices, near-centre residential, city centre, and port industrial areas. District flows are demand proxies and may include losses. No Bengaluru/Gangtok locations, supply observations, pipe geometry or transfer capacities have been invented.

The full source includes the original competition's evaluation periods. Requiem defines its own chronological 70/15/15 split and explicitly separates model selection from final scoring. Its reported score must not be described as a BWDF leaderboard result. Calendar features are evaluated in UTC for this prototype.

Weather is retained as an original source file but is not a feature in the current model. To add it, use weather inputs available at each forecast origin and evaluate them separately; future observed weather would leak information.
