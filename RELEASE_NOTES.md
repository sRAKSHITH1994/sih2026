# SIH26073 final release verification

Version: 3.0.0 — 2026-09-18

## Verified

- 12 backend/API/model tests passed.
- React production dashboard compiled successfully.
- Dual TP and TPH LSTM artifacts load and perform inference.
- Exact Shapley output names and normalizes all active atmospheric channels.
- Station simulator uses the production telemetry schema and source isolation.
- “Warning before station dies” reaches pre-failure/red-alarm state in an automated API test.
- Current Local Brain C++ sources passed strict host syntax checking.
- Both SHT31 and DHT22 builds plus rain, wind, vane and solar conditional paths passed strict host syntax checking.
- Nine-scenario injected Global benchmark: 97.44% balanced accuracy, 97.37% F1, 100% precision, 94.88% recall and 0% false-alarm rate in the supplied seeded run.
- Group-held-out edge MLP test: 90.05% accuracy, 89.82% balanced accuracy and 88.89% macro F1 on generated fault-profile data.

## Target-build note

The complete PlatformIO build command was attempted, but the isolated build environment could not download `espressif32@7.1.3` because all PlatformIO registry mirrors timed out. This is why strict C++ host checks and optional-configuration checks were also run. On the development laptop, PlatformIO must complete its one-time toolchain/library download before upload.

## Claim boundary

The reported metrics are injected/generated software-validation results. Physical calibration, outdoor weather comparison, real unplug/freeze/power/movement experiments and long-duration false-alarm/energy/lead-time measurements remain required before claiming field accuracy.
