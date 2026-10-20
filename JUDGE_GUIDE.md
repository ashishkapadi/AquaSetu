# Explain Requiem to the judges

## A 45-second introduction

“Requiem turns historical water consumption into a demand forecast, compares it with an operator's available supply, and recommends how to allocate that supply across zones. The dashboard also flags consumption that is unusual relative to the forecast. We separate the learned demand prediction from the allocation calculation, so both the evidence and the decision can be explained.”

“We used the open Water-Futures / BWDF benchmark with 10 measured districts. We converted hourly flow rates into hourly water volumes and tested next-hour predictions on a later period the model had not trained on.”

We switched from the suggested Kaggle competition because it required account-side access steps. The problem statement permits relevant alternative datasets. BWDF is especially suitable because it has genuine district-level time series. Cite https://github.com/WaterFutures/wf4bwdf and Alvisi et al. (2025), DOI `10.1061/JWRMD5.WRENG-6887`.

## Our measured result

- Source: 19,679 hourly timestamps, 10 real districts, 196,790 district-hour rows including missing values.
- Unit: cubic metres consumed/inflow volume per hour, converted from hourly mean L/s by multiplying by 3.6.
- Initial training examples: 101,142; validation: 28,876; final test: 29,081. Lag requirements and missing measurements reduce the usable counts.
- Final next-hour test MAE: **3.10 m³ per district-hour**.
- Same-hour-last-week baseline MAE: **4.32 m³**.
- Improvement: **28.35% lower MAE**. This is not “96.9% accuracy.”
- Test dates: **28 November 2022, 22:00 UTC to 31 March 2023, 21:00 UTC**.
- Latest forecast origin: **31 March 2023, 21:00 UTC**. The demo is historical replay.
- Latest-hour anomaly flags: zero. Ten unusual readings are present in the previous 72 hours; use the historical-alert panel to explain one.
- These are our holdout results, not the benchmark's original leaderboard evaluation.

## What does training mean?

We create many examples from the history. The inputs describe what was known before a particular hour: recent consumption, consumption at the same hour yesterday and last week, and calendar information. The answer is how much water was actually consumed during that hour.

The model learns relationships between those inputs and answers. Our gradient-boosted trees learn a sequence of small decision trees; each additional tree helps correct errors left by the earlier ones. We use a compact model suitable for a laptop.

## Why these inputs?

Recent consumption captures momentum. Yesterday and last week's readings capture recurring patterns. Calendar features help separate hours and weekdays. Rolling means describe the recent level while smoothing some noise. These choices are hypotheses about useful patterns; the validation score tells us whether the learned model improves on the baseline.

## How do you know the model works?

We divide the data chronologically: earlier history for training, a later validation period for selecting the method, and a final test period for reporting performance. We do not randomly shuffle time series.

Our baseline repeats the same hour from last week. We select the boosted-tree model only if its validation MAE is lower. MAE means mean absolute error: our prediction misses the actual district-hour volume by about 3.10 m³ on average on the final test set.

The reported score tests next-hour forecasts. Each forecast can use readings already observed before that hour. For longer horizons we repeatedly feed predictions back as inputs, so errors may accumulate. We do not claim the one-hour score proves 24-hour accuracy.

The Model Analysis page now separately tests recursive horizons at five eligible origins across all ten districts. At 24 hours, hourly MAE is **3.538 m³** versus **4.367 m³** for the weekly baseline (19.0% lower). Mean error in total 24-hour district volume is **33.269 m³** versus **43.719 m³**. This is a limited sample of 1,200 district-hour predictions, not the full next-hour test. Eight weekly origins were predetermined across the test period; three were excluded because of missing targets or unresolved historical gaps. These origins share a weekly time position, so results do not establish performance for every possible forecast start time.

An honest finding: at six hours the model improves hourly MAE, but its total-volume error is slightly worse than the baseline (12.311 versus 12.163 m³). Explain that a model can predict the hourly shape better while still slightly overestimating the total. We expose both measures because allocation depends on totals.

Use the district table to explain why aggregate scores are insufficient: DMA 3 improves by only 5.0%, while DMA 2 improves by 33.8%. Larger absolute error in a high-volume district is not automatically worse relative performance. Bias is prediction minus observation; positive means overprediction. RMSE emphasizes large misses.

The UI organization draws inspiration from [Shadcn Admin](https://github.com/satnaing/shadcn-admin). District and horizon evaluation is informed by [WaterFutures' evaluation implementation](https://github.com/WaterFutures/wf4bwdf/blob/main/src/wf4bwdf/_solution_evaluation.py). We implemented our own models, chronological split and diagnostics; these are not their competition scores.

## How do alerts work?

We compare an observation against the expected consumption and flag unusually large errors using a threshold learned from validation errors. An alert can indicate an unexpected event, a faulty sensor or a leak; without further evidence we cannot distinguish them.

## How is water distributed?

Demand is forecast by ML; allocation is an explicit constrained calculation. We distribute the shared supply according to demand and operator-assigned priority, cap each allocation at its predicted demand, and keep the total at or below available supply.

Example: two zones each need 100 units; 120 are available. Equal priority yields 60 each. Raising one zone's priority gives it a larger share, but another zone receives less. The total shortage remains 80: redistribution cannot create water.

The high/medium/low risk labels summarize allocation coverage: below 75%, 75% to below 95%, and at least 95%. They are transparent planning thresholds, not probabilities predicted by a classifier.

## What is real versus simulated?

- Consumption/inflow and evaluation come from the real BWDF district histories. Inflow is a proxy for district demand and can include network losses.
- Forecasts start after the last timestamp in that file, not necessarily today.
- Available supply and priority weights are user-entered scenarios unless a measured source is provided.
- The current app uses 10 real districts with separately trained models. The importer also supports a single series, but would explicitly label derived zones as simulated in that case.
- Units must match the dataset documentation. No invented liters or cubic metres.
- The zone schematic is not a geographic map.
- Weather is not currently a model input.

## A two-minute demo

1. Identify the dataset, date range, documented units and whether zones are measured or simulated.
2. Show historical consumption beside the next-hour forecast.
3. Show the selected method and compare test MAE with the weekly baseline.
   Open the recent unusual-readings panel: at 11:00 UTC on 31 March 2023, DMA 6 recorded 47.95 m³ against an expectation of 35.72 m³. The 12.23 m³ difference exceeded its 9.85 m³ threshold. Call it an unusual reading, not a confirmed leak.
4. Lower available supply. Point to the total shortage and zone coverage.
5. Increase one zone's priority. Show exactly how allocations change while total water is conserved.
6. Set supply to zero and then above total demand. Show clear shortages and unused supply.
7. Explain one limitation and next step: real zone meters and network capacity constraints would make recommendations more operationally useful.

## Likely questions

**How does the changing map work?** Each illustrative area represents a measured district series. The trained model supplies future hourly demand; the allocation algorithm recomputes demand coverage as the supply or district priorities change. Red means under 75% covered, amber 75% to under 95%, green at least 95%. Green may still have a small shortage. These are coverage categories, not statistical probabilities.

On the Area Map page, select a district and increase its priority to show the tradeoff with other districts. Start 24-hour forecast playback to watch peak-hour demand change the coverage colors. The hourly supply is the selected scenario's total supply divided by its horizon, held constant for each playback hour. Playback uses saved predictions, not live measurements. Unused water does not carry forward, and pipes or storage are not modeled. The boundaries are illustrative because the supplied data does not include verified district geometry.

Map demo: choose the 1-hour horizon, enter 800 m³ supply, and set DMA 1 (Hospital) priority to 5. Enable forecast playback. Hour 1 is fully covered across all districts. Seek to hour 11 (1 April 2023 at 08:00 UTC): predicted system demand rises to approximately 1,065.3 m³, leaving 265.3 m³ uncovered; the hospital stays green while the other nine areas turn red. This illustrates changing demand and prioritization with the same hourly water budget.

**Why no deep learning?** We chose a compact model that can be trained and evaluated reliably within the hackathon deadline. More complex models would need evidence of improvement, not just a different name.

**Does this prevent shortages?** It forecasts likely demand and exposes an expected deficit under a supply scenario. It recommends allocation; it cannot guarantee supply or prevent every sudden surge.

**What happens if patterns change?** Recent lag features allow forecasts to respond as new observations arrive, and large forecast errors can trigger alerts. The current prototype retrains when a new CSV is imported; it does not include a live sensor stream or automatic retraining service.

**Can the recommendations actually be sent through pipes?** We do not model pipe capacity or pressure. This prototype is a planning tool. A production version would add a network model and operational constraints.
