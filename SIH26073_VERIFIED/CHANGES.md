# Complete change inventory

Built from ORIGINAL. No frontend file is changed. Every delivered text file is supplied in full and every text change is in `CHANGESET.diff`; binary files are supplied in full and hashed in `docs/delivery_manifest.json`. The diff does not recursively include itself. The manifest excludes its own hash and the two generated inventory/diff files to avoid circular hashes.

The portable ZIP keeps the original project folders and run-script names. It excludes the old machine-specific Python environment, PlatformIO outputs, native compiler binaries, caches and SQLite WAL/SHM files. Committed original database records are retained in the migrated database; rebuild host libraries with `scripts/build_native.py`. These runtime packaging exclusions are not silently removed project source.

Rejected model variants are retained only as reproducibility checkpoints under `artifacts/experiments`; deployed header/NPZ and server metadata identify the chosen model. The historical audit is clearly separate from the current repair status.

| File | Change | Why |
| --- | --- | --- |
| `CHANGES.md` | added | Complete file-by-file repair inventory and packaging notes. |
| `CHANGESET.diff` | added | Complete unified text diff; binary artifacts are supplied in full. |
| `README.md` | modified | Current architecture, honest scope and remaining limitations. |
| `RELEASE_NOTES.md` | modified | Withdraw invalid old benchmark claims and explain the actual release. |
| `REPAIR_STATUS.md` | added | Evidence and fixed/partial/hardware status for every A/B finding. |
| `SIH26073_MPU_POSITION_ADDITION/START_HERE.md` | modified | Explain that the MPU addition is already integrated and must not be reapplied. |
| `SIH26073_MPU_POSITION_ADDITION/apply_addition.py` | modified | Prevent the older addition from overwriting already-repaired integrated firmware. |
| `START_HERE_WINDOWS.md` | modified | PowerShell setup, retraining/tests, dashboard and hardware instructions. |
| `VERSION.txt` | modified | Identify the repaired ten-class version. |
| `backend/app/evaluation.py` | modified | Independent raw-input sample/event benchmark, computed coverage, delays and timing. |
| `backend/app/global_brain.py` | modified | Equipment priority, minute cadence/TP fallback, continuous LSTM fusion and trained second opinion. |
| `backend/app/local_reference.py` | added | Actual exported MLP/features and compiled portable rules with parity-tested fallback; Windows DLL lookup. |
| `backend/app/lstm_autoencoder.py` | modified | Contiguous window training support and cadence/provenance persistence. |
| `backend/app/main.py` | modified | Safe static serving/auth, identity/order/freshness guards, additive API presentation and original routes. |
| `backend/app/schemas.py` | modified | Validate finite/required observations and packet identity; retain frontend request/response fields. |
| `backend/app/sensor_registry.py` | modified | Sensor source/freshness/validity and actual processing status. |
| `backend/app/simulator.py` | modified | Raw channel stimuli only; retain original scenario/action contract and optional profiles. |
| `backend/app/spatial.py` | modified | Known/fresh/source-matched multi-channel neighbour corroboration. |
| `backend/app/storage.py` | modified | Idempotent storage/migration, historical archive, anomaly episodes and safe acknowledgement/export. |
| `backend/data/global_brain.db` | modified | Migrate committed original records; preserve reports and backfill explicitly historical events. |
| `backend/models/edge_second_opinion.joblib` | added | Trained model or command-generated LSTM/second-opinion/integrated/native measurement artifact. |
| `backend/models/edge_second_opinion.json` | added | Trained model or command-generated LSTM/second-opinion/integrated/native measurement artifact. |
| `backend/models/evaluation_metrics.json` | modified | Trained model or command-generated LSTM/second-opinion/integrated/native measurement artifact. |
| `backend/models/lstm_metrics.json` | added | Trained model or command-generated LSTM/second-opinion/integrated/native measurement artifact. |
| `backend/models/lstm_tp_autoencoder.npz` | modified | Trained model or command-generated LSTM/second-opinion/integrated/native measurement artifact. |
| `backend/models/lstm_tph_autoencoder.npz` | modified | Trained model or command-generated LSTM/second-opinion/integrated/native measurement artifact. |
| `backend/models/native_metrics.json` | added | Trained model or command-generated LSTM/second-opinion/integrated/native measurement artifact. |
| `backend/requirements.txt` | modified | Compatible pinned/ranged dependencies, including weighted sklearn API and pandas 2.x/3.x. |
| `backend/tests/conftest.py` | added | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `backend/tests/test_api.py` | modified | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `backend/tests/test_migration.py` | added | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `backend/tests/test_native_parity.py` | added | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `backend/tests/test_real_training.py` | added | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `backend/tests/test_repair_contract.py` | added | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `backend/tests/test_sensor_registry.py` | modified | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `backend/tests/test_spatial.py` | modified | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `backend/tests/test_temporal.py` | added | Regression evidence for the repaired API, inference, storage, chronology, class masks or native parity. |
| `docs/API_COMPATIBILITY.md` | added | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/ARCHITECTURE.md` | modified | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/ARCHIVE_DIFF_ALL.tsv` | added | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/EVALUATION.md` | modified | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/HARDWARE_CONNECTIONS.md` | modified | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/INVENTORY.md` | added | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/REPAIR_PLAN.md` | added | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/VALIDATION.md` | added | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/delivery_manifest.json` | added | Original/delivered SHA-256 and byte-size evidence for project files. |
| `docs/frontend_original_sha256.json` | added | Repair inventory/contract/plan or current architecture, hardware, evaluation and validation documentation. |
| `docs/verification/browser_results.json` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/commands.json` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/database_migration.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/edge_final_audit.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/edge_training_exploratory.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/frontend_comparison.json` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/frozen_evaluation.png` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/frozen_hardware.png` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/frozen_live.png` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/frozen_simulator.png` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/integrated_evaluation.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/label_ablation.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/lstm_training.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/native_benchmark.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/platformio_download_failure.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/pytest.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/pytest_pandas3.log` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `docs/verification/runtime.json` | added | Executed verification output, screenshot, command record or runtime/hash evidence; scope stated in VALIDATION.md. |
| `edge_training/README.md` | modified | Exact classes/features, label convention, commands and limits. |
| `edge_training/artifacts/edge_mlp.joblib` | modified | Actual selected model/scaler, held-out sample export, locked selection or command-generated audit/ablation metrics. |
| `edge_training/artifacts/edge_mlp.npz` | added | Actual selected model/scaler, held-out sample export, locked selection or command-generated audit/ablation metrics. |
| `edge_training/artifacts/edge_mlp_metrics.json` | modified | Actual selected model/scaler, held-out sample export, locked selection or command-generated audit/ablation metrics. |
| `edge_training/artifacts/edge_scaler.joblib` | modified | Actual selected model/scaler, held-out sample export, locked selection or command-generated audit/ablation metrics. |
| `edge_training/artifacts/edge_training_sample.csv` | modified | Actual selected model/scaler, held-out sample export, locked selection or command-generated audit/ablation metrics. |
| `edge_training/artifacts/experiments/seed_0/large_regularized.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_0/large_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_0/large_weighted.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_0/server_boosting.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_0/small_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_0/split_manifest.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_0/validation.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_1/large_regularized.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_1/large_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_1/large_weighted.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_1/server_boosting.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_1/small_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_1/split_manifest.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_1/validation.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_2/large_regularized.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_2/large_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_2/large_weighted.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_2/server_boosting.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_2/small_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_2/split_manifest.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_2/validation.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_3/large_regularized.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_3/large_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_3/large_weighted.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_3/server_boosting.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_3/small_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_3/split_manifest.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_3/validation.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_4/large_regularized.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_4/large_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_4/large_weighted.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_4/server_boosting.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_4/small_resample.joblib` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_4/split_manifest.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/experiments/seed_4/validation.json` | added | Reproducible per-seed training/validation checkpoint or split manifest; nonselected models are experiments only. |
| `edge_training/artifacts/label_ablation_metrics.json` | added | Actual selected model/scaler, held-out sample export, locked selection or command-generated audit/ablation metrics. |
| `edge_training/artifacts/original_edge_mlp.npz` | added | ORIGINAL header arrays parsed into NPZ for the documented shifted-corpus baseline. |
| `edge_training/artifacts/selection_locked.json` | added | Actual selected model/scaler, held-out sample export, locked selection or command-generated audit/ablation metrics. |
| `edge_training/corpus.py` | added | Current-observation labels, recovery intervals, realistic normal variation and sensor profiles. |
| `edge_training/feature_pipeline.py` | modified | Preserve 56 formulas/order with mask sanitation, float32 raw input and gap resets matching C++. |
| `edge_training/inference.py` | added | Run exported float32 arrays and gate all optional classes by sensor masks. |
| `edge_training/requirements.txt` | modified | Compatible pinned/ranged dependencies, including weighted sklearn API and pandas 2.x/3.x. |
| `edge_training/train_edge_mlp.py` | modified | Grouped five-seed selection/comparison, held-out metrics/events and matched exports. |
| `firmware/include/config.h` | modified | Version/model dimensions, bounded queue/payload settings, nominal rail and bus defaults. |
| `firmware/include/data_types.h` | modified | Carry the actual 56-feature vector for the server second opinion. |
| `firmware/include/detection_rules.h` | added | Portable shared rule core for firmware and native benchmark. |
| `firmware/include/model_weights.h` | modified | Generated selected 56-64-32-10 weights/scaler; same arrays as NPZ. |
| `firmware/include/sensor_manager.h` | modified | Expose checked sensor and MPU diagnostics/reset/scan interfaces. |
| `firmware/include/trusted_data.h` | modified | Accepted-observation baseline and separate estimate/expiry API. |
| `firmware/src/edge_mlp.cpp` | modified | Generated hidden dimensions, all ten classes and sensor-valid output gating. |
| `firmware/src/feature_engine.cpp` | modified | Matched masks/gap reset/stable feature accumulation without changing the 56-feature order. |
| `firmware/src/health_engine.cpp` | modified | Preserve ten-class sensor attribution and describe risk as a heuristic health index. |
| `firmware/src/local_brain.cpp` | modified | Real rules/model fusion, explicit warmup, trust acceptance and no backlog-driven physical risk. |
| `firmware/src/main.cpp` | modified | Current version and truthful health-index serial text. |
| `firmware/src/recovery_manager.cpp` | modified | Indefinite exponential retries capped at 60 seconds and three-read recovery. |
| `firmware/src/sensor_manager.cpp` | modified | Checked MPU identity/reset/ranges/reads and consistent I2C recovery diagnostics. |
| `firmware/src/station_position.cpp` | modified | Integrate scan/reset diagnostics with persistent calibrated position workflow. |
| `firmware/src/telemetry.cpp` | modified | Acquisition identity/time, persistent acknowledged priority backlog, diagnostics and feature telemetry. |
| `firmware/src/trusted_data.cpp` | modified | Three accepted observations before promotion, suspect separation and expiring invalid estimates. |
| `firmware/tests/native_benchmark.cpp` | added | Plain-g++ harness/stub for actual feature/model/rule, recovery/trusted or position logic; no ESP32 claim. |
| `firmware/tests/native_replay.cpp` | added | Plain-g++ harness/stub for actual feature/model/rule, recovery/trusted or position logic; no ESP32 claim. |
| `firmware/tests/native_rules.cpp` | added | Plain-g++ harness/stub for actual feature/model/rule, recovery/trusted or position logic; no ESP32 claim. |
| `firmware/tests/native_stub/Arduino.h` | added | Plain-g++ harness/stub for actual feature/model/rule, recovery/trusted or position logic; no ESP32 claim. |
| `firmware/tests/test_position.cpp` | added | Plain-g++ harness/stub for actual feature/model/rule, recovery/trusted or position logic; no ESP32 claim. |
| `firmware/tests/test_recovery_trusted.cpp` | added | Plain-g++ harness/stub for actual feature/model/rule, recovery/trusted or position logic; no ESP32 claim. |
| `scripts/ablate_spike_labels.py` | added | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/browser_smoke.py` | added | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/build_native.py` | added | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/make_repair_report.py` | added | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/measure_native.py` | added | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/migrate_database.py` | added | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/package_repair.py` | added | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/run_evaluation.py` | modified | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/run_native_tests.py` | added | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/send_demo_telemetry.py` | modified | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `scripts/train_lstm.py` | modified | Reproducible migration, training, evaluation, native/browser verification, measured reporting or portable packaging command. |
| `sih26073_code_audit.md` | added | Preserved historical REFERENCE audit used during inventory. |
| `start_dashboard.bat` | modified | Preserve BAT workflow with one-time dependency marker and error handling. |
| `start_dashboard.sh` | modified | Preserve shell workflow with one-time dependency marker and error handling; executable mode. |

Unchanged files, including all frontend paths and preserved datasets/configuration, are listed with equal hashes in the manifest. See `REPAIR_STATUS.md` for remaining hardware/field/UI limitations and `docs/EVALUATION.md` for measurements; a file change alone is not evidence that hardware was tested.
