# Windows PowerShell workflow

Extract the ZIP into a new folder. Open that folder in VS Code and open **Terminal → New Terminal**. The terminal must be in the folder containing `backend`, `firmware`, `edge_training`, `scripts` and `frontend`. Keep the original project as your backup. Do not copy the old Windows `.venv` into this folder.

## Set up Python once

Use Python 3.12. These commands call the environment interpreter directly, so PowerShell activation policy is irrelevant.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r edge_training\requirements.txt
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
```

NumPy 2.x and pandas 2.x/3.x are supported. The weighted MLP API requires the pinned scikit-learn 1.8.0. Install PlatformIO through its separate VS Code environment; its Python dependencies can conflict with dashboard dependencies if installed into the same environment.

## Run the dashboard with the supplied trained models

```powershell
.\start_dashboard.bat
```

Open `http://127.0.0.1:8000`. Keep the terminal open. Later, run the same BAT again; no retraining or frontend rebuild is necessary. The script creates/updates its dependency marker once. Never run `npm install` or `npm run build` for this repair: the supplied ORIGINAL frontend is frozen.

Upload the repaired firmware before using hardware packets as current observations. Older firmware without a boot identity is archived as unverified and cannot advance live inference; the original records remain available as history. The simulator can be used before the firmware upload.

Local simulation/evaluation buttons receive a loopback-only HttpOnly credential when you open `/`. Telemetry and reset still require the station token. A browser opened remotely by LAN IP cannot obtain this local credential; send an explicit `X-Station-Token` for remote write API calls. Read routes remain compatible with the original dashboard.

## Native compiler and tests

A native `g++` must be on PATH (for example an existing MinGW-w64 installation). The VS Code editor alone does not supply it. If you already installed MSYS2 UCRT64, its usual compiler path is `C:\msys64\ucrt64\bin`; prepend that existing directory to PATH if necessary. No ESP32 SDK is needed for these tests.

```powershell
g++ --version
.\.venv\Scripts\python.exe scripts\run_native_tests.py
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

`run_native_tests.py` fails clearly when g++ is absent. The general pytest suite can skip native tests without g++; do not call that an equivalent native pass. The simulator has a Python portable-rule fallback verified by the parity tests. The reproducible CLI benchmark below explicitly requires compiled firmware rules.

## Retrain and reproduce the measurements

Run these in another terminal after stopping the dashboard, so its cached models cannot remain old:

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
.\.venv\Scripts\python.exe edge_training\train_edge_mlp.py --jobs 5
.\.venv\Scripts\python.exe scripts\ablate_spike_labels.py --jobs 5
.\.venv\Scripts\python.exe scripts\train_lstm.py --threshold-percentile 97
.\.venv\Scripts\python.exe scripts\run_native_tests.py
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe scripts\run_evaluation.py --samples-per-scenario 220 --stations 3 --seed 42 --sessions-per-class 16
.\.venv\Scripts\python.exe scripts\measure_native.py
.\.venv\Scripts\python.exe scripts\make_repair_report.py
.\start_dashboard.bat
```

`--jobs 1` uses less memory and is slower; it preserves split seeds. The training comparison uses 48 training, 16 validation and 32 final test sessions per class per seed. Seeds 0–4 train five models; final audit sessions use a disjoint seed namespace with offset 100. Deployment always exports training seed 0. No row from the test sessions enters training or early stopping. The original diagnostic label bug is deliberately reintroduced only by the separate ablation script, never the deployment trainer.

The LSTM command supports `--tp-threshold-percentile` and `--tph-threshold-percentile` overrides, plus `--sweep 90 95 97 98 99 99.2 99.5`. Select thresholds using validation or predeclared operational requirements, never by selecting the best test table row. Its minute CSVs are under `backend/data`; their original acquisition provenance is unverified. Real field claims require independent collection and labels.

## Build and upload ESP32-S3

The main `firmware` folder already integrates the MPU addition. **Do not reapply the legacy addition** or copy its older files over repaired firmware.

Edit only your needed Wi-Fi settings and laptop IPv4 (`ipconfig`) in `firmware/include/user_config.h`. Preserve or deliberately configure `ENABLE_EXTERNAL_HUMIDITY=1`, `HUMIDITY_SENSOR_TYPE=HUMIDITY_DHT11`, DATA GPIO 4 for the supplied DHT11 setup. The frozen dashboard's printed IP is an old example; use your actual laptop IPv4.

With the existing PlatformIO VS Code installation used in the original workflow:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -d firmware
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -d firmware --target upload
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -d firmware --baud 115200
```

Close any other COM11 serial monitor before uploading. These commands still require the platform packages to download successfully. The ESP32 build/upload was not completed in the repair environment; only native portable logic was compiled and timed here.

After valid MPU reads appear, place the station in its fixed demo pose, type `I2CSCAN`, inspect diagnostics, and type `MPUCAL` for 30 settled samples. `SENSORSRESET` reinitializes interfaces. Record `MPUINFO`, sustained tilt, return-to-pose, unplug/reconnect, Wi-Fi outage, reboot and power-interruption trials. Read `docs/HARDWARE_CONNECTIONS.md`.

For collection, first create the output folder and close competing serial monitors:

```powershell
New-Item -ItemType Directory -Force logs
.\.venv\Scripts\python.exe edge_training\collect_serial.py --port COM11 --seconds 900 --output logs\field.csv
```

Detector output labels in this CSV are predictions, **not independent ground truth**. Annotate real sessions separately before training. The `real_dataset` validation helper checks manually supplied `ground_truth`, `session_id`, `split` and timestamp continuity; the default comparison command above generates synthetic sessions.
