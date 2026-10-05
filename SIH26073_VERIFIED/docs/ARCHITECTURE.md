# Architecture and actual model capabilities

## Local Brain

The ESP32-S3 acquires a 1 Hz snapshot, retains a 20-sample raw window, and computes the same ordered 56 features as `edge_training/feature_pipeline.py`. Invalid groups are zero-filled only inside numeric features, with explicit masks; they are never published as real zero observations. Trusted estimates do not enter the feature extractor.

The trained float32 MLP is 56 → 64 ReLU → 32 ReLU → 10 softmax outputs. Its classes are NORMAL, SPIKE, DRIFT, FROZEN, ERRATIC, ELECTRICAL, MECHANICAL, RAIN_BLOCKED, WIND_SEIZED, VANE_STUCK. Electrical/motion/rain/wind/vane outputs are gated by INA/MPU/rain/wind/vane validity. Atmospheric inference needs a complete valid BMP window. The original feature ordering is retained; no frozen-channel-count feature or blanket prediction debounce was added.

Portable rules run alongside the MLP. Physical data loss, health state, communication backlog and calibrated station position are separate mechanisms. Gradient × input reports local feature contributions; the model's softmax and the heuristic health index are not calibrated probabilities. Link backlog does not raise physical health risk.

Self-healing consists of bounded sensor reinitialization, retry backoff capped at 60 seconds, and confirmation by three consecutive valid reads. A trusted baseline is promoted only after three accepted observations with a ready feature window. Suspect raw data remains separate; last-value estimates expire after ten seconds and never become valid observed data. Rain is never imputed. This is not an autonomous actuator or a learned reconstruction guarantee.

Telemetry includes a random boot ID, sequence, acquisition time or monotonic age, validity, diagnostics, and the exact 1 Hz feature vector. A six-item RAM queue feeds a 96-record LittleFS backlog. Writes use a temporary file, flush/close and rename; acknowledged records are removed. An independent latest-critical slot is tried before backlog over HTTP and optional LoRa. Overflow/file failure has explicit drop reporting. No filesystem is automatically formatted unless the partition is fully erased. Physical power-cut durability and flash wear are unverified; unsaved RAM can still be lost.

## Global Brain

The backend validates finite sensor values, archives unverified/old/out-of-order packets, and deduplicates boot/sequence identities before updating inference. Legacy packets lacking boot identity are archived instead of being silently certified fresh. SQLite preserves raw packets, decisions, acquisition/receipt times, and anomaly episodes with recovery and acknowledgement state.

TP and TPH LSTM autoencoders receive completed 60-second snapshots. Each 20-step sequence covers roughly 19 minutes of observations; gaps/invalid readings reset continuity. TP continues while the independent TPH window fills. Thresholds are validation percentiles; `scripts/train_lstm.py` writes a percentile sweep with validation and held-out test precision/recall/counts. Continuous normalized reconstruction evidence is fused with edge evidence rather than requiring an LSTM hard-threshold gate. These fusion scores are uncalibrated.

A hist-gradient-boosted server model is trained on the same grouped sessions as the edge model. Its 50/50 second opinion with the MLP was retained after validation improvement in all five runs. On hardware it consumes the transmitted 1 Hz feature vector, not a newly invented window from slower HTTP packets. It remains unavailable for old firmware that does not supply that vector.

Spatial evidence requires known locations, matching source, fresh aligned measurements, at least two independent neighbours, and matching direction/magnitude in at least two atmospheric channels. Equipment, position, missing-data and physical-range evidence takes precedence. Matching weather is corroboration, not proof; shared sensor biases and sparse networks remain field-validation risks.

The host simulator generates raw stimuli then executes feature/ML/rule processing. It never assigns faults from scenario names. Its physical health/recovery/pose state machines are excluded explicitly. CLI evaluation uses compiled firmware rules; dashboard evaluation can use the parity-verified portable Python rule implementation if no native compiler/library is present, and records which path ran.

## Frozen dashboard limits

Every ORIGINAL frontend file is unchanged, including its stale dist. Backend presentation copies expose safe display sentinels and typed nullable `observations` plus availability flags, while stored packets retain their original values. The original charts still filter invalid points, join across gaps, and space points by index; backend metadata cannot fix that rendering code. Hardcoded probability, risk and stability labels remain. Source/freshness and readiness are supplied in API fields and explanatory text. New anomaly/MPU information is accessible through API/export, not new pages.
