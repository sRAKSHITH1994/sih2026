# Evaluation criteria and anomaly-injection protocol

| Criterion | Weight | Evidence implemented |
|---|---:|---|
| Innovation & Novelty | 25 | Edge MLP + rule fusion, warning-before-death, adaptive sensor masks, dual global model |
| Detection Accuracy | 20 | Accuracy, balanced accuracy, precision, recall, F1, specificity, confusion matrix |
| Real-Time Capability | 15 | Local inference on-device; Global mean/p95 latency and throughput |
| Explainability | 10 | Fault type, affected sensor, gradient×input edge features, exact Shapley Global attribution |
| Scalability | 10 | Per-station state, SQLite history, asynchronous telemetry, optional added channels/stations |
| Practical Deployability | 10 | ESP32-S3, offline queue, recovery, current sensor profile, Wi-Fi and optional LoRa alert |
| Visualization / UI | 5 | Live, Evaluation, Hardware and labelled Simulator pages |
| Energy Efficiency | 5 | INA219 live voltage/current/power and pre-failure maintenance warning |

## Edge MLP validation

`edge_training/train_edge_mlp.py` builds grouped full sequences for ten classes and multiple sensor-attachment profiles. Entire sequences—not shuffled rows—are assigned 70%/15%/15% to train/validation/test groups to limit temporal leakage. The supplied model test result is approximately 90.1% accuracy, 89.8% balanced accuracy and 88.9% macro F1. Exact values are in the artifact JSON.

This training data is generated fault-profile data. Replace or fine-tune it with captured physical data using `edge_training/collect_serial.py` before making field-accuracy claims.

## Global injected benchmark

`scripts/run_evaluation.py` uses held-out normal atmospheric sequences and controlled normal, spike, drift, frozen, data-loss, electrical, mechanical, station-power-degradation and genuine multi-station weather scenarios. Neighbour packets pass through the same Global engine rather than being inserted as a hidden fake-neighbour flag.

Run `python scripts/run_evaluation.py` or press **Run injected benchmark** on the dashboard. The included JSON records its seed, scenario results, confusion matrix and latency.

## Field protocol still required

Before the final claim, record:

1. normal outdoor sessions covering changing temperature/pressure and, after attachment, humidity;
2. safe BMP unplug/reconnect, spike, frozen-stream replay, power sag and movement tests;
3. a reference weather source or calibrated reference instrument;
4. false alarms per hour/day, detection delay, recovery time, Wi-Fi loss, queue recovery, current consumption and pre-failure warning lead time;
5. photos/logs identifying the physical test and configuration.

The dashboard intentionally labels generated and injected results. Do not present them as certified real-weather accuracy or an official SIH score.
