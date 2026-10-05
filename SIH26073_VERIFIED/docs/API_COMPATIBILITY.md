# Frozen ORIGINAL frontend contract

Inspected all `fetch`/`jsonFetch` uses and field reads in ORIGINAL `frontend/src/App.jsx` before backend edits. The production dist is also preserved without rebuilding. No frontend source, asset, package or branding edits are permitted.

| Route | Required shape and fields | Compatibility handling |
|---|---|---|
| GET /api/v1/stations | stations[], stale_seconds; each station: station_id, station_name, received_at, age_seconds, reporting, packet, decision, inference_ms | Keep all; source/freshness/time-quality fields additive |
| GET /api/v1/stations/{id}/history?limit=120 | station_id, history[]; entries packet.sensors | Keep default source inference from selected station; preserve acquisition timestamp; canonical nulls added separately |
| GET /api/v1/stations/{id}/hardware | station_id, firmware_version, link, last_report, sensors[] | Keep; sensors are array, never dictionary |
| POST /api/v1/simulation/step | input scenario, reset, include_humidity, mirror_station_id; output ok, scenario, generated_packets, simulation_index, target | target retains packet/decision/inference_ms/id/received_at; uses real MLP |
| POST /api/v1/evaluation/run | input samples_per_scenario, stations, seed | Preserve every evaluation field below; provenance added |
| GET /api/v1/evaluation/latest | available; same evaluation payload | Exclude invalid old benchmark claims |
| Other ORIGINAL routes | GET health, architecture, simulation/scenarios; POST telemetry, reset; WS /api/v1/ws | Preserve paths and original response keys |

Nested fields:
- packet: station_id, station_name, firmware_version, source_mode, sensors, link, local_brain.
- sensors.bmp280.values: temperature_c, pressure_hpa; humidity: sensor_type, values.humidity_pct; ina219.values: power_mw, bus_voltage_v, current_ma; mpu6050.values.accel_z_ms2.
- hardware.sensors[]: key, label, sensor_type, attached, valid, status, processed_by_ml.
- packet.link: rssi_dbm.
- local_brain: anomaly, fault_type, severity_score, severity_level, confidence, explanation, affected_sensors, warmup_complete, ml_valid, ml_class, ml_class_name, ml_probability, ml_top_features, failure_risk_score, station_state, trust_score, pre_failure_warning, alarm_state, maintenance_action, ewma_score, cusum_score.
- decision: anomaly, genuine_weather, category, specific_type, confidence, explanation, evidence.
- evidence.lstm: profile, ready, anomaly, reason, loss, threshold; evidence.spatial: status, neighbor_count, supporting_neighbors, explanation; evidence.xai.global_method.
- evaluation: binary_metrics.{balanced_accuracy,f1}, latency.{p95_inference_ms,throughput_per_second}, criteria[] (name,value), confusion.{tn,fp,fn,tp}, samples, warning, scenarios[] (scenario,detected,detection_latency_samples).

## Constraints which backend changes cannot fully satisfy

`fmt(null)` displays zero; `Number(null)` plots zero. Legacy display fields use an em dash sentinel where a value is unavailable, with typed nullable observations and availability flags supplied separately. Valid numeric values remain numeric. Confidence retains a safe numeric zero with `confidence_available=false` and an explicit uncalibrated/heuristic confidence kind; explanations disclose the limitation. Browser and formatter-contract tests verify the original frontend does not crash on these unavailable values.

Sparkline filters invalid points and computes X from array indices. Backend cannot make it break paths or use acquisition-time spacing. The API provides nullable invalid observations, acquisition timestamps and a gap threshold in `chart_contract`, but B8 chart rendering remains partial. No manipulation of HTML or response JavaScript bypasses the freeze.

Static UI labels include failure risk, ML probability, Normal reconstruction and Atmospheric conditions are stable. API explanatory text/readiness is corrected; those labels remain unchanged. There is no anomaly-history page in the frozen frontend; history is available via additive API/export.

Simulation/evaluation POSTs send no token. Local dashboard compatibility uses an HttpOnly, same-origin loopback session minted by `/`, cryptographically tied to the station token and validated for those two routes only; explicit station token is required for hardware/reset and remote writes. Cross-origin writes and untrusted Host headers fail tests. This scoped browser credential is the explicit local compatibility exception; clients visiting by remote LAN IP do not receive it.
