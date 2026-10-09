# Measured evaluation — synthetic and supplied-data evidence

The integrated system caught **269/274 injected events (98.18%)** in independent synthetic sessions. Its per-sample binary accuracy was **91.83%**, with **2916/25896 normal samples falsely alerted (11.26%)**. Report these together. The high event rate does not imply high per-sample accuracy, correct fault typing, or a low false-alarm burden.

The selected ESP32 MLP alone achieved **89.16 ± 1.18% ten-class per-sample accuracy** across five held-out seeds and **2381/2446 (97.34%) event detection**. A >98% per-sample claim is not supported. None of these numbers establishes field accuracy or a calibrated failure probability. The old slide's 97.4%, 0/388, 67.74 ms and 27.77 KB must be replaced, not carried forward.

Re-render this report after reproducing the commands below with `python scripts/make_repair_report.py`. JSON artifacts retain full precision, per-seed results and confusion matrices. Percentages and delays in this document are calculated from those artifacts.

## Commands and splits

Run from the project root, using the environment interpreter. On PowerShell use `.\.venv\Scripts\python.exe` in place of `python`. Set `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1` for comparable CPU contention.

```text
python edge_training/train_edge_mlp.py --jobs 5
python scripts/ablate_spike_labels.py --jobs 5
python scripts/train_lstm.py --threshold-percentile 97
python scripts/run_native_tests.py
python scripts/run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16
python scripts/measure_native.py
python scripts/make_repair_report.py
```

The recorded final edge audit was produced with `python edge_training/train_edge_mlp.py --finalize-only` after the five-seed training comparison; this reuses the included train/validation checkpoints without fitting on test. A full run of the first command repeats both fitting and finalization. The initial exploratory run exposed test results before the stricter consistency selection rule was settled; those results are not the final reported audit. The final model choice was locked using validation, then a fresh test namespace with run-seed offset 100 was evaluated. This procedural change is disclosed rather than describing the entire development process as a pristine preregistered experiment.

For each training seed 0–4: 48 train, 16 validation and 32 final test sessions per class; ten classes; 220 raw 1 Hz observations per session. Entire sessions belong to one split. The first 19 observations warm the feature window and are excluded from MLP classification metrics, not labelled as model successes. Training, validation, test and integrated evaluation use disjoint seed namespaces. Normalization fits training only; external whole-session validation selects epochs. No onset or recovery rows are removed after warmup. The selected artifact always uses training seed 0, not whichever seed scores best on test.

Humid dry periods, calm wind and fixed vane direction are deliberate NORMAL controls. Multi-channel weather fronts remain NORMAL. Humidity includes whole-percent and fine-resolution profiles. Missing channels are zero-filled only inside the masked feature vector; they are not represented as valid zero observations. Rain, wind and vane classes remain in all model outputs and are gated when their corresponding sensor is invalid.

Final MLP audit: 1600 complete held-out sessions, 321600 eligible observations across the five seeds. Split manifests are in `edge_training/artifacts/experiments/seed_*/split_manifest.json`. Raw sessions regenerate deterministically from the manifest seeds and `corpus.py`.

## Ten-class per-sample results

| Model | Accuracy % mean ± SD | Balanced accuracy % | Macro-F1 % | Binary accuracy % |
| --- | --- | --- | --- | --- |
| original | 25.04 ± 0.87 | 21.60 ± 1.47 | 18.47 ± 1.45 | 51.62 ± 1.14 |
| small_resample | 87.80 ± 0.66 | 90.45 ± 1.19 | 85.43 ± 0.67 | 88.59 ± 0.54 |
| large_resample | 88.15 ± 0.56 | 89.48 ± 0.82 | 85.88 ± 0.55 | 88.99 ± 0.51 |
| large_weighted | 89.16 ± 1.18 | 89.03 ± 1.15 | 86.88 ± 1.20 | 89.94 ± 1.20 |
| large_regularized | 89.07 ± 1.41 | 87.40 ± 2.07 | 86.43 ± 1.70 | 90.05 ± 1.19 |
| server_boosting | 96.91 ± 0.56 | 97.13 ± 0.74 | 96.21 ± 0.56 | 96.99 ± 0.54 |
| server_blend | 96.40 ± 0.46 | 96.81 ± 0.64 | 95.61 ± 0.37 | 96.57 ± 0.44 |

SD is the sample standard deviation across five seeds, not a confidence interval over correlated rows. `original` is the ORIGINAL exported weight/scaler arrays evaluated on the new, harder corpus through the current mask-compatible feature implementation. It is a distribution-shift baseline, not a reproduction of the ORIGINAL small-test score and not a controlled estimate of one repair's benefit. Server boosting and the 50/50 blend use the same train/validation/test sessions as the MLP. They are host models, not ESP32 models. Boosting alone scores better than the fixed blend on this audit; it is retained as a second opinion, not used to replace the embedded model based on test results.

### Per-class recall before and after

| Class | ORIGINAL weights on new corpus % | Same 64-32 model, buggy SPIKE training labels % | Corrected selected model % mean ± SD |
| --- | --- | --- | --- |
| NORMAL | 26.96 | 74.65 | 89.45 ± 2.07 |
| SPIKE | 2.11 | 84.04 | 89.96 ± 2.79 |
| DRIFT | 2.07 | 77.79 | 84.21 ± 5.81 |
| FROZEN | 0.11 | 46.69 | 49.54 ± 7.14 |
| ERRATIC | 75.43 | 95.17 | 95.62 ± 1.76 |
| ELECTRICAL | 34.05 | 99.87 | 99.93 ± 0.10 |
| MECHANICAL | 19.67 | 98.89 | 99.33 ± 0.26 |
| RAIN_BLOCKED | 39.20 | 91.12 | 93.31 ± 1.82 |
| WIND_SEIZED | 12.77 | 96.40 | 98.69 ± 1.68 |
| VANE_STUCK | 3.68 | 88.25 | 90.31 ± 1.92 |

### Changes and measured effects

- **Labels (kept):** the controlled train-only label ablation changes ten-class accuracy 80.65% → 89.16%, SPIKE recall 84.04% → 89.96%, and NORMAL recall 74.65% → 89.45%; validation and test always use correct labels.

- **64-32 weighted loss (kept):** validation macro-F1 improves in four of five seeds over 24-12 resampling; final audit macro-F1 85.43% → 86.88%; balanced accuracy declines 90.45% → 89.03%. Selection optimizes macro-F1, not every metric.

- **64-32 resampling (not deployed):** validation improves in only three of five seeds; final macro-F1 85.88%. A small mean gain did not meet the consistency rule.

- **Stronger regularization/longer patience (not deployed):** alpha .01 and patience 40 improve validation in only three of five seeds versus weighted alpha .001/patience 20; final macro-F1 86.43% is below the retained model. Alpha and patience were tested together, so their individual causal effects are not identified.

- **Server second opinion (kept):** the fixed 50/50 blend improves validation macro-F1 in all five seeds; final MLP/blend macro-F1 86.88% → 95.61%.

- **Realism and grouped splits (required):** these change the validity and difficulty of the evaluation; no isolated accuracy gain is claimed. No derived frozen-channel feature or blanket debounce was introduced. FROZEN onset/recovery ambiguity remains unresolved; do not compare its harder current recall directly with the earlier easy-corpus recall.

- **Continuous LSTM fusion (implemented, operational gain unmeasured):** the short integrated sessions never warm the minute model. Unit tests verify score continuity and precedence, not an accuracy improvement. Keep this distinction in presentations.

### Confusion matrix

Aggregate counts across the five held-out MLP runs; rows are true labels and columns are predictions. The order is the full ten-class list.

| True / predicted | NORMAL | SPIKE | DRIFT | FROZEN | ERRATIC | ELECTRICAL | MECHANICAL | RAIN_BLOCKED | WIND_SEIZED | VANE_STUCK |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NORMAL | 144827 | 702 | 1862 | 4895 | 2001 | 14 | 367 | 2758 | 1169 | 3297 |
| SPIKE | 99 | 1582 | 1 | 0 | 77 | 0 | 0 | 0 | 0 | 0 |
| DRIFT | 2239 | 19 | 16536 | 17 | 380 | 0 | 3 | 360 | 3 | 85 |
| FROZEN | 9004 | 0 | 25 | 9818 | 0 | 2 | 0 | 347 | 4 | 624 |
| ERRATIC | 635 | 183 | 36 | 0 | 18797 | 0 | 1 | 0 | 1 | 2 |
| ELECTRICAL | 14 | 0 | 0 | 0 | 0 | 19667 | 0 | 0 | 0 | 0 |
| MECHANICAL | 124 | 0 | 3 | 3 | 0 | 0 | 19730 | 3 | 0 | 1 |
| RAIN_BLOCKED | 1142 | 0 | 33 | 45 | 0 | 0 | 0 | 18394 | 0 | 99 |
| WIND_SEIZED | 248 | 0 | 6 | 3 | 0 | 0 | 0 | 0 | 19500 | 1 |
| VANE_STUCK | 1771 | 0 | 30 | 108 | 0 | 0 | 0 | 7 | 4 | 17892 |

## MLP-only event detection

An event is one injected fault interval. A hit is any non-NORMAL MLP prediction during that interval; typed hits require the correct class at least once. A prediction already active at onset may count as a zero-delay hit. No post-event allowance is used. Delays are from injection onset to first hit, conditional on detected events; misses are counted separately. The MLP-only event metric uses argmax without the operational confidence threshold, rules or server fusion.

| Fault | Detected / events | Rate | Correct-type hits | Median delay s | p95 delay s |
| --- | --- | --- | --- | --- | --- |
| SPIKE | 1124/1166 | 96.40% | 1082 | 0.0 | 0.0 |
| DRIFT | 158/160 | 98.75% | 156 | 4.0 | 12.2 |
| FROZEN | 139/160 | 86.88% | 127 | 13.0 | 32.0 |
| ERRATIC | 160/160 | 100.00% | 160 | 0.0 | 1.0 |
| ELECTRICAL | 160/160 | 100.00% | 160 | 0.0 | 0.0 |
| MECHANICAL | 160/160 | 100.00% | 160 | 0.0 | 0.0 |
| RAIN_BLOCKED | 160/160 | 100.00% | 160 | 0.0 | 9.0 |
| WIND_SEIZED | 160/160 | 100.00% | 160 | 0.0 | 1.0 |
| VANE_STUCK | 160/160 | 100.00% | 160 | 5.0 | 15.0 |

## Integrated raw-stimulus benchmark

The deployment seed-0 MLP runs on raw stimuli through the Python feature extractor whose parity is checked against C++, the actual exported float32 weights, compiled C++ firmware rules, and Global Brain including its trained second opinion. No scenario name or ground-truth label is passed to the detector. 13 scenario types × 16 sessions × 220 observations produce 45760 target observations; neighbouring stations bring the total to 137280 processed packets. Evaluation reset boundaries are whole sessions. This additional evaluation namespace is disjoint from fitting and model selection.

Binary truth means sensor/equipment fault. Genuine weather is negative. Raw power sag and missing data are included; a complete powerless radio-silent station is not simulated by the power-sag scenario. Physical ESP32 health/recovery/position behavior, storage, transport and browser time are excluded. LSTM-ready target observations: **0**; its separate minute-window audit follows below.

| Binary metric | Value |
| --- | --- |
| accuracy | 91.83% |
| balanced_accuracy | 92.30% |
| precision | 86.72% |
| recall | 95.85% |
| specificity | 88.74% |
| false_alarm_rate | 11.26% |
| f1 | 91.06% |

| Actual / predicted | Normal | Fault |
| --- | --- | --- |
| Normal | 22980 | 2916 |
| Fault | 824 | 19040 |

| Scenario | Events caught / total | Correct-type hits | Median / p95 delay s | False alerts / normal samples |
| --- | --- | --- | --- | --- |
| normal | no injected fault | — | — | 162/3520 |
| spike | 109/114 | 108 | 0.0 / 0.0 | 601/3350 |
| drift | 16/16 | 16 | 6.0 / 9.2 | 332/1523 |
| frozen | 16/16 | 16 | 18.0 / 22.0 | 137/1558 |
| erratic | 16/16 | 16 | 0.0 / 2.0 | 109/1539 |
| electrical | 16/16 | 16 | 0.0 / 0.0 | 307/1620 |
| mechanical | 16/16 | 16 | 0.0 / 0.2 | 170/1508 |
| rain_blocked | 16/16 | 16 | 0.0 / 6.0 | 175/1550 |
| wind_seized | 16/16 | 16 | 0.0 / 0.0 | 27/1512 |
| vane_stuck | 16/16 | 16 | 7.0 / 15.2 | 82/1598 |
| data_loss | 16/16 | 16 | 0.0 / 0.0 | 70/1551 |
| genuine_weather | no injected fault | — | — | 435/3520 |
| station_power_failure | 16/16 | 0 | 3.5 / 10.2 | 309/1547 |

Measured explanation coverage is 21956/21956 = 100.00%: alerts with nonempty text plus feature attribution, affected-sensor evidence, or invalid-feature evidence. This is a presence/coverage measure, not a test that explanations are causally correct. `normal.detected` is computed from false alerts, and is false in this run.

The weather test still produces false alarms despite stricter spatial confirmation. Its safeguards are verified in `test_spatial.py` and equipment-precedence tests; field discrimination quality is not established. Correct-type counts use the final decision's exact `specific_type`; composite/physical range categories may catch an event without matching its injected class name.

## LSTM threshold audit

Command: `python scripts/train_lstm.py --threshold-percentile 97`. TP and TPH use 20 completed one-minute snapshots, stride one snapshot; live inference uses the same cadence and resets on gaps. A ready TP model remains active while TPH accumulates sufficient humidity history. Training uses only contiguous normal train windows; normal validation windows set each profile's threshold. Test windows never fit weights or thresholds. Supplied CSV acquisition provenance is unverified. A window is positive if any of its original 20 rows is anomalous; overlapping windows are not independent events.

The selected percentile 97 follows the user's requested operating point before this audit; per-profile percentile overrides are supported but were not tuned on the test table. The following table is diagnostic, not an instruction to pick the best test result. Thresholds differ by profile even when the percentile is shared.

| Profile | Normal train windows | Normal validation windows | All test windows | Threshold at selected percentile |
| --- | --- | --- | --- | --- |
| TP | 15015 | 3194 | 3706 | 0.00338208303 |
| TPH | 15015 | 3194 | 3682 | 0.00375437923 |

| Profile | Percentile | Validation precision | Validation recall | Test precision | Test recall | Test FP / negatives |
| --- | --- | --- | --- | --- | --- | --- |
| TP | 90 | 48.39% | 58.25% | 77.13% | 54.16% | 83/3189 |
| TP | 95 | 64.76% | 57.09% | 95.10% | 52.61% | 14/3189 |
| TP | 97 | 74.93% | 55.73% | 97.46% | 52.03% | 7/3189 |
| TP | 98 | 81.07% | 53.20% | 100.00% | 51.64% | 0/3189 |
| TP | 99 | 89.40% | 52.43% | 100.00% | 50.10% | 0/3189 |
| TP | 99.2 | 91.22% | 52.43% | 100.00% | 49.90% | 0/3189 |
| TP | 99.5 | 94.35% | 51.84% | 100.00% | 49.13% | 0/3189 |
| TPH | 90 | 52.10% | 71.02% | 86.02% | 64.91% | 52/3189 |
| TPH | 95 | 67.94% | 69.18% | 95.17% | 63.89% | 16/3189 |
| TPH | 97 | 77.36% | 66.94% | 100.00% | 62.47% | 0/3189 |
| TPH | 98 | 83.46% | 65.92% | 100.00% | 61.26% | 0/3189 |
| TPH | 99 | 90.83% | 64.69% | 100.00% | 60.04% | 0/3189 |
| TPH | 99.2 | 92.40% | 64.49% | 100.00% | 60.04% | 0/3189 |
| TPH | 99.5 | 95.18% | 64.49% | 100.00% | 60.04% | 0/3189 |

- TP, same retrained model: 99.2 → 97 percentile changes test recall 49.90% → 52.03%, false alarms 0 → 7. This is not a rerun of the old incorrectly cadenced benchmark.

- TPH, same retrained model: 99.2 → 97 percentile changes test recall 60.04% → 62.47%, false alarms 0 → 0. This is not a rerun of the old incorrectly cadenced benchmark.

Continuous fusion uses the reconstruction-loss/threshold ratio, maps it to `ratio/(1+ratio)`, and combines it with the edge score as `1-(1-edge)*(1-lstm)`. Its result is an uncalibrated evidence score. The fusion decision threshold is a documented heuristic, not a learned failure probability. Equipment, pose, range and missing-data evidence take precedence over weather confirmation.

## Replacement slide numbers and measurement boundaries

| Slide item | Measured value | Exact command | Measures | Does NOT measure |
| --- | --- | --- | --- | --- |
| Detection | 269/274 = 98.18% event detection; 91.83% binary sample accuracy | python scripts/run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16 | Held-out injected events and target samples through real MLP, compiled rules and server | Field accuracy, exact fault typing, ESP32 hardware, ready LSTM |
| False alarms | 2916/25896 = 11.26% | python scripts/run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16 | Normal target samples falsely flagged, including weather and recovery | False events per day or field specificity |
| Host pipeline latency | mean 5.954 ms; p95 8.351 ms | python scripts/run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16 | Synchronous features + MLP/rules + server CPU time | ESP32 or network/radio/database/browser/end-to-end delay |
| Model array payload | 24232 weight/bias bytes + 448 normalization bytes = 24680 bytes (24.1016 KiB) | python scripts/measure_native.py | Native sizeof the exact float arrays compiled from model_weights.h | Entire firmware flash image, linker padding/code/RAM or header text size |
| Native firmware MLP latency | mean 0.05728 ms; p95 0.08926 ms | python scripts/measure_native.py | Host g++ -O2 runEdgeML over independent held-out features, including scaling/masks/softmax/attribution | Feature extraction, transport or ESP32 timing |

Native timing: 6030 held-out feature vectors; g++ (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0; Linux-6.18.44-x86_64-with-glibc2.39. Header source text is 108688 bytes, distinct from the float-array payload. The final model NPZ SHA-256 is `c5f415b96e57a51215f7f63ba425dc8245c7d6005778cb4273353fd435471e15`. Wall-clock latency varies by host/load; reproduce rather than treating these decimals as universal constants.

## Verification and remaining work

See `VALIDATION.md`, `REPAIR_STATUS.md` and `verification/` for the actual logs. The ORIGINAL frontend is byte-identical, including its stale production dist. Browser checks covered its four pages, simulation and evaluation POSTs, with no JavaScript page errors. The backend serves that original dist; it does not rebuild it.

Physical work remaining: complete an ESP32 PlatformIO build/upload; measure on-device flash, stack/heap and timing; verify BMP/DHT/INA/MPU reads and electrical ranges; test persistent calibration, actual pose changes and I2C failures; exercise indefinite recovery retries with three valid reads; power-cut LittleFS writes and acknowledgements; test queue saturation, flash wear, reboot replay and LoRa gateway delivery; collect independently labelled multi-station field sessions, including difficult normal plateaus, sensor gaps and weather fronts. The native build does not certify any of these physical behaviors.

The frozen UI prevents gap-breaking/acquisition-time chart rendering and removal of hardcoded confidence/risk labels. The API provides availability, source, freshness, timestamps and honest explanations, but those visual limitations remain. No frontend byte was changed to hide them.

## Five judge questions and truthful answers

1. **Is 98.18% your accuracy?** No. It is event detection on injected held-out sessions. Binary per-sample accuracy is 91.83%; ten-class edge accuracy is 89.16 ± 1.18% across seeds.

2. **Did you achieve zero false alarms?** No. This integrated run produced 2916 false alert samples out of 25896 normal target samples. Consecutive alerts are correlated, so this is not a false-event rate per day.

3. **Were labels or rules used to fake model success?** Labels only generate stimuli and score output; inference receives raw values, masks and packet context. It runs trained weights and compiled firmware rules. Explanation coverage measures evidence presence, not causal correctness.

4. **Are latency and model size measured on ESP32?** No. Native sizeof gives the float-array payload, and host C++/Python timings are reported separately. ESP32 build/download, upload and physical timing remain unverified.

5. **What is the largest remaining model weakness?** FROZEN per-sample recall is 49.54%; onset windows and legitimate plateaus remain ambiguous. The LSTM has limited recall too. Event detection cannot substitute for field calibration or correct sample labels.
