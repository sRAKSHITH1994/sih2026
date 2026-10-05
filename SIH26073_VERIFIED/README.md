# SIH26073 — repaired ten-class Local + Global Brain

This package starts from ORIGINAL and retains its entire `frontend/` byte-for-byte. It keeps the original top-level directories, run-script names, DHT11 configuration, and MPU addition folder. The reference repair supplied reviewed implementation ideas; its seven-class model and changed dashboard were not adopted.

Start with `START_HERE_WINDOWS.md`. Read `REPAIR_STATUS.md` for fixed, partial and hardware-dependent findings. `docs/EVALUATION.md` contains reproducible numbers, scopes, per-class recall and event delay. `CHANGES.md` lists every changed file; `CHANGESET.diff` contains complete unified text diffs.

The edge model is **56 → 64 → 32 → 10**, with NORMAL, SPIKE, DRIFT, FROZEN, ERRATIC, ELECTRICAL, MECHANICAL, RAIN_BLOCKED, WIND_SEIZED and VANE_STUCK. Optional classes remain present and are masked when their sensors are invalid. DATA_LOSS, COMMUNICATION_FAULT, STATION_DEGRADATION and position faults are separate rule/state outputs, not additional MLP classes.

The server uses TP/TPH LSTM autoencoders on completed 60-second snapshots, source-isolated spatial corroboration, and a validation-selected gradient-boosted second opinion on the transmitted 1 Hz feature vector. It does not reconstruct a 1 Hz feature window from slower HTTP arrival order. Equipment, position and data-loss faults take precedence over weather corroboration. Spatial agreement is evidence, not proof of genuine weather.

All included new accuracy claims are controlled held-out results. There is no demonstrated >98% per-sample field accuracy, calibrated confidence, calibrated failure probability, or established warning horizon. The simulator computes real features/weights/rules; it does not emulate the physical health/recovery/pose state machines. Benchmark scopes and false alarms must accompany event detection percentages.

The original 5,885 stored reports are preserved; 33 historical anomaly episodes are backfilled and explicitly historical. Read `/api/v1/anomalies` or `/api/v1/anomalies/export.csv`. The frozen frontend has no anomaly-history page.

The frozen frontend also cannot render acquisition-time chart gaps, remove its hardcoded probability/risk/stability labels, or expose new MPU diagnostics. API fields and explanations are corrected; these display limitations remain. `docs/API_COMPATIBILITY.md` records the exact contract and limits. The backend serves the ORIGINAL production dist, which still differs from its source; no rebuild was performed.

Use the dashboard locally at `http://127.0.0.1:8000`. Its simulation/evaluation buttons use a same-origin, HttpOnly, loopback-only credential bound to the configured station token. Remote writes and telemetry/reset require `X-Station-Token`. This preserves local button operation without exposing the token in JavaScript or making remote writes public. Change firmware/backend tokens together if you configure your own token.

Software tests are included. ESP32 flashing, MPU wiring/calibration, power interruption and LoRa tests require the physical board. The attempted ESP32 cross-build did not complete because toolchain downloads failed. See the captured build logs and the native validation results; native success is not an ESP32 build or timing result.
