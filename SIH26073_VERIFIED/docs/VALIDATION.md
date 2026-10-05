# Executed validation

The full backend/portable-native suite passed: **52 tests**, with one dependency deprecation warning. The targeted pandas 3.0.6 temporal/real-data suite passed: **6 tests**, with the same warning. The main suite used pandas 2.2.3. Actual output is preserved in `verification/pytest.log` and `verification/pytest_pandas3.log`; versions are in `verification/runtime.json`. These are software test counts, not accuracy measurements.

## Tests and what they establish

```text
python scripts/run_native_tests.py
python -m pytest backend/tests -q
python SIH26073_MPU_POSITION_ADDITION/apply_addition.py --project . --check
```

The native script first builds the real portable C++ rule core with g++, then runs native parity/recovery/position tests. It requires a compiler and fails clearly without one. The general pytest suite may skip native tests when g++ is unavailable; no native tests were skipped in the recorded complete run. The legacy addition check reported already installed and made no changes.

Tests cover API route/shape compatibility, unavailable-value formatting, static traversal, tokenless/cross-origin writes, physical range overrides, source separation, stale/old/duplicate/reboot packets, archive migration and acknowledgements, spatial evidence requirements, equipment priority, TP-to-TPH readiness, minute cadence/gaps, pandas datetime units, label conventions, disjoint session manifests, all ten class masks, and native feature/model/rule parity. Native recovery/trusted tests exercise persistent retry/backoff, three-read recovery, baseline rejection/promotion and estimate expiry; position tests exercise the portable pose state machine.

The C++ parity replay compares all 56 features, model class, winning score and rule type across ten generated fault classes. Float feature comparisons use rtol/atol 0.002 and model-score comparisons 0.005; predicted classes and rule types must agree exactly after warmup. This checks numerical implementation parity, not sensor I/O or an ESP32 firmware build.

To repeat both pandas versions in PowerShell after setup:

```powershell
.\.venv\Scripts\python.exe -m pip install "pandas==2.2.3"
.\.venv\Scripts\python.exe -m pytest backend\tests\test_temporal.py backend\tests\test_real_training.py -q
.\.venv\Scripts\python.exe -m pip install "pandas==3.0.6"
.\.venv\Scripts\python.exe -m pytest backend\tests\test_temporal.py backend\tests\test_real_training.py -q
```

The recorded alternate-version check placed pandas 3.0.6 in a separate import directory so the main environment stayed on pandas 2.2.3. Both are allowed by the requirements. Native timing uses g++ 13.3.0; numerical/training and timing differences across hosts remain possible.

## Frozen frontend and browser

`diff -r ORIGINAL/frontend SIH26073_VERIFIED/frontend` returned exit code 0. All **10 files** have matching SHA-256 hashes; names and bytes match, not just appearance. `frontend_original_sha256.json` is the test fixture; `verification/frontend_comparison.json` records the final comparison. No npm install/build was performed. Source/dist staleness is intentionally retained.

Browser command:

```text
python scripts/browser_smoke.py --start-server
```

This starts a disposable backend/database, loads ORIGINAL production dist, visits Live Intelligence, Evaluation Criteria, Hardware Integration and Station Simulator, exercises simulation/evaluation through the browser's scoped credential, and checks page errors. `verification/browser_results.json` records successful original HTML serving, ELECTRICAL simulation output, compatible evaluation output and an empty page-error list. Four screenshots are included. The small browser evaluation is a smoke check, not the headline benchmark. The production database was not reset for it.

Optional setup to reproduce the browser check (not needed to start the dashboard):

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts\browser_smoke.py --start-server
```

The browser ran before final additive availability/stale-sensor metadata refinements; the subsequent complete API suite covers those refinements, including invalid numeric placeholders and preservation of raw values. The frontend bytes did not change. Windows PowerShell and physical hardware were not available here; Windows command paths, normalized hash paths and native DLL dependency lookup were reviewed, not falsely described as executed Windows tests.

## Model/evaluation evidence

`EVALUATION.md` gives commands and all measured accuracy, confusion, event, delay, size and timing results. Its tables are rendered by `scripts/make_repair_report.py` from JSON. Included logs distinguish the initial exploratory edge comparison from the final fresh held-out audit. The label-only ablation was run separately and never replaces deployment weights. The LSTM sweep includes both validation and untouched test-window metrics.

Native sizeof is the float-array payload, not total linked ESP32 flash. Native runEdgeML timing excludes feature extraction; integrated host timing includes feature/local/global compute but excludes network, SQLite, browser and ESP32. The integrated sessions do not warm the minute LSTM. No ground-truth label enters inference.

## Database preservation

The original database was backed up through SQLite into a separate working database and migrated. `verification/database_migration.log` records **5885 reports preserved**, **33 historical events** and an unchanged source. Historical recorded classifications remain marked as history; they were not relabelled as validated new-model decisions. Read-only migration tests also verify preservation and CSV formula protection. WAL/SHM runtime files are not portable deliverables; committed state is in the migrated database.

## What did not pass or was not run

`python -m platformio run -d firmware` did not complete. The platform and one toolchain downloaded, but a required RISC-V toolchain failed checksum/download attempts and timed out. The download log is `verification/platformio_download_failure.log`. No full ESP32 compiler, linker, upload, heap/stack or on-device timing pass is claimed.

LittleFS power-loss/rename/acknowledgement behavior, FreeRTOS memory pressure, Wi-Fi outages, actual LoRa gateway delivery, sensor electrical behavior, MPU identity/calibration persistence, real resets and physical self-healing remain untested on hardware. Native tests exercise portable logic, not those interfaces. See `REPAIR_STATUS.md` for partial findings and `HARDWARE_CONNECTIONS.md` for the hardware workflow.
