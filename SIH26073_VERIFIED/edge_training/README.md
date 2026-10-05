# Ten-class edge training

The deployed network is 56 → 64 → 32 → 10 (ReLU hidden layers, softmax output). `train_edge_mlp.py` exports the same float32 arrays to `artifacts/edge_mlp.npz` and `firmware/include/model_weights.h`. Firmware dimensions come from the generated header. `inference.py` runs those exported arrays; the simulator never substitutes scenario labels for predictions.

## Commands

```text
python -m pip install -r edge_training/requirements.txt -r backend/requirements.txt
python edge_training/train_edge_mlp.py --jobs 5
python scripts/ablate_spike_labels.py --jobs 5
python scripts/run_native_tests.py
python scripts/measure_native.py
python scripts/make_repair_report.py
```

Use `--jobs 1` if memory is limited. Default training and metrics are synthetic. The loader `real_dataset(path)` validates externally annotated `ground_truth`, `session_id`, `split`, timestamps, channel values and validity masks, but it is not exposed as a real-data training CLI. Collected detector labels are predictions, never independent truth. Add a separately reviewed field training workflow before claiming field learning.

## Labels and sensor masks

SPIKE labels only the 1–2 modified samples of each injected event. Its return transition and following tail are NORMAL. Persistent faults are labelled from onset inclusive to recovery exclusive; recovery is immediately NORMAL even while features retain window history. There is no onset grace period. This intentionally exposes detection lag and residual-window false alarms.

Profiles are core, core_humidity, wind, rain and full. BMP/MPU/INA are core; optional weather channels are absent according to profile. The feature-valid mask gates ELECTRICAL by INA, MECHANICAL by MPU, RAIN_BLOCKED by rain, WIND_SEIZED by wind and VANE_STUCK by vane. All ten output classes remain. BMP is required for a ready 20-observation feature window. Nonfinite/invalid raw channels are sanitized identically in Python/C++; a gap over 2500 ms restarts window readiness and adaptive state.

The corpus varies seeds, noise floors, levels, diurnal phase, genuine multi-channel weather fronts, humidity quantization and installed sensors. Normal calm wind, fixed vane and humid-without-rain controls deliberately overlap optional faults. No derived frozen-channel count or blanket prediction debounce was added. Full label, split, selection and measured limitation details are in `../docs/EVALUATION.md`.

## Exact output class order

| Index | Class |
| --- | --- |
| 0 | NORMAL |
| 1 | SPIKE |
| 2 | DRIFT |
| 3 | FROZEN |
| 4 | ERRATIC |
| 5 | ELECTRICAL |
| 6 | MECHANICAL |
| 7 | RAIN_BLOCKED |
| 8 | WIND_SEIZED |
| 9 | VANE_STUCK |

## Exact 56-feature input order

| Index | Feature |
| --- | --- |
| 0 | temperature |
| 1 | temperature_delta |
| 2 | temperature_std |
| 3 | temperature_slope |
| 4 | pressure |
| 5 | pressure_delta |
| 6 | pressure_std |
| 7 | pressure_slope |
| 8 | humidity |
| 9 | humidity_delta |
| 10 | humidity_std |
| 11 | humidity_slope |
| 12 | acceleration_norm |
| 13 | acceleration_std |
| 14 | acceleration_jerk |
| 15 | gyro_norm |
| 16 | bus_voltage |
| 17 | bus_voltage_delta |
| 18 | bus_voltage_std |
| 19 | current_ma |
| 20 | current_delta |
| 21 | current_std |
| 22 | power_mw |
| 23 | power_slope |
| 24 | ewma_temperature |
| 25 | ewma_pressure |
| 26 | ewma_humidity |
| 27 | normalized_residual_temperature |
| 28 | normalized_residual_pressure |
| 29 | normalized_residual_humidity |
| 30 | cusum_temperature |
| 31 | cusum_pressure |
| 32 | cusum_humidity |
| 33 | wind_speed |
| 34 | wind_speed_std |
| 35 | wind_speed_slope |
| 36 | wind_zero_fraction |
| 37 | wind_gust_factor |
| 38 | wind_direction_sin |
| 39 | wind_direction_cos |
| 40 | wind_direction_circular_variance |
| 41 | wind_direction_stuck_fraction |
| 42 | rain_rate |
| 43 | rain_window_accumulation |
| 44 | rain_humidity_inconsistency |
| 45 | solar_irradiance |
| 46 | solar_std |
| 47 | solar_clear_ratio |
| 48 | bmp_valid |
| 49 | humidity_valid |
| 50 | mpu_valid |
| 51 | ina_valid |
| 52 | rain_valid |
| 53 | wind_valid |
| 54 | vane_valid |
| 55 | solar_valid |

The window remains 20 one-second observations. The feature formulas/order remain the ORIGINAL 56-feature design; raw mask sanitation, gap resets and numerically stable accumulators are matched in `feature_pipeline.py` and `firmware/src/feature_engine.cpp`. Native tests compare all features, predicted class, score and portable-rule output across all ten fault classes. No unreviewed feature is appended.
