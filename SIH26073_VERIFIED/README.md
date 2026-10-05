# Sky Guard AI — SIH26073

**AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)**
Smart India Hackathon 2026 — Problem Statement 26073
Team: **Super Tech Titans**

---

## Problem

Automatic Weather Stations (AWS) feed the data that agencies like IMD and NDMA use for forecasting and disaster response — but they fail silently. A stuck sensor, a corroded contact, or a power fault can produce readings that look like normal variation, so bad data reaches downstream systems unflagged. Worse, a genuine severe-weather event and a local sensor fault can look identical from a single station's data alone. Conventional AWS quality checks (fixed range/threshold rules) cannot tell the two apart, and faults are typically only caught by manual inspection — long after the data has already been trusted.

## Our Solution

A two-layer **Local Brain / Global Brain** system:

- **Local Brain (ESP32-S3, on the station):** A compact ML classifier plus statistical checks (EWMA, CUSUM) classify every 20-second window into one of 10 states — normal, or one of 9 distinct fault types — entirely on-device, with no internet connection required. Alerts are queued locally (LittleFS) and delivered once connectivity returns.
- **Global Brain (FastAPI server):** An LSTM autoencoder adds a second-opinion anomaly check, and a **spatial cross-check** compares each station's readings against its own recent trend and against nearby stations before confirming a weather-driven event — this is how the system tells a genuine storm front apart from an isolated equipment fault.

### Two Core Innovations

1. **Weather-vs-Fault Spatial Discrimination** — An anomaly is only confirmed as genuine weather if at least two known, nearby, recently-reporting stations show matching direction and magnitude of change across at least two weather channels. A station already reporting an equipment fault is excluded as corroborating evidence for its neighbours.
2. **Self-Healing Data Pipeline with Trust Verification** — A suspect sensor channel is isolated and retried with exponential backoff, and only restored to full trust after **three consecutive valid readings** — a single good reading doesn't instantly clear a fault. Raw, invalid, and fallback readings are stored and displayed separately, preserving full data traceability.

## Repository Structure

```
.
├── backend/              FastAPI server — ingestion, Global Brain (LSTM, spatial check), API, tests
│   ├── app/
│   ├── data/             train/val/test CSVs, runtime database (gitignored — see Setup)
│   ├── models/           trained LSTM weights + evaluation metrics
│   └── tests/
├── edge_training/        Synthetic data generator, feature pipeline, edge MLP training + artifacts
├── firmware/              ESP32-S3 firmware (PlatformIO)
│   ├── src/, include/
│   └── tests/            native (PC-side) C++ tests — no ESP32 hardware required to run these
├── frontend/              React dashboard (do not restructure — see Known Issues)
├── scripts/               Training/evaluation/demo helper scripts
└── docs/                  Evaluation methodology, release notes
```

## Tech Stack

| Layer | Technology |
|---|---|
| Edge firmware | C++ (Arduino framework), ESP32-S3, PlatformIO |
| Edge inference | Hand-written NumPy-compatible MLP (no heavyweight ML runtime on-device) |
| Sensors | BMP280 (temp/pressure), DHT-class humidity, MPU6050 (tilt/tamper), optional anemometer/rain gauge/vane |
| Server | Python, FastAPI, NumPy-based LSTM autoencoder (no external deep-learning framework dependency), SQLite |
| Frontend | React |
| ML tooling | scikit-learn (training only), custom synthetic session generator |

## Setup (Windows / PowerShell)

### 1. Environment
```powershell
cd SIH26073_VERIFIED
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
pip install -r edge_training\requirements.txt
```

### 2. Backend
```powershell
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Open the dashboard at **http://localhost:8000** (not `0.0.0.0` — that address only has meaning to the server, not a browser).

### 3. Frontend
The dashboard is served by the backend from a pre-built `frontend/dist`. If you change anything in `frontend/src`, rebuild before it will show up:
```powershell
cd frontend
npm install
npm run build
```
Restart the backend afterward.

### 4. Firmware
```powershell
cd firmware
pio run --target upload
```
Requires the ESP32-S3 connected via USB and PlatformIO installed (CLI or the VS Code extension). Station identity (`STATION_ID`, `STATION_NAME`) is set in `firmware/include/user_config.h` — give every physical board a unique `STATION_ID`.

### 5. Native firmware tests (no hardware needed)
Requires a C++ compiler (`g++`) on PATH — install via `winget install -e --id BrechtSanders.WinLibs.POSIX.UCRT` if you don't have one, then **open a new terminal window** before continuing (PATH changes don't apply to an already-open shell).
```powershell
cd SIH26073_VERIFIED
python scripts\run_native_tests.py
```
This compiles the firmware's fault-detection logic as a host `.dll`/`.so` and checks it produces identical results to the Python reference implementation.

### 6. Retraining / re-evaluating the edge model (optional)
```powershell
python edge_training\train_edge_mlp.py
python scripts\train_lstm.py --threshold-percentile 97
```

## Using the Dashboard

- **Live Intelligence** — real-time view of all connected stations (real or simulated), current readings, and the fused Local + Global Brain decision.
- **Station Simulator** — a controlled digital twin that sends the exact telemetry schema the real ESP32 uses, clearly marked `SIMULATED DATA — NOT HARDWARE` and isolated from real spatial evidence. Use this to demo any of the 10 fault scenarios, including `Genuine Weather — Three-station weather event`, which is the counterpart demo showing the spatial check correctly identifying a real weather event instead of a fault.
- **Evaluation Criteria** / **Hardware Integration** — supporting reference views.

## Evaluation Methodology and Honest Results

We evaluate on independent, held-out synthetic test sessions — grouped by whole session (no session used for tuning is reused for scoring), averaged over multiple random seeds, validation-tuned and test-confirmed. We report what we measure, not what we hoped for:

| Metric | Result |
|---|---|
| Event-level detection rate | **98.2%** (269 of 274 injected fault events) |
| Per-sample 10-class accuracy | ~89.8% |
| Integrated binary (fault vs. normal) accuracy | ~91.8% |
| False-alarm rate on fault-free data | ~11% (actively being worked on — see below) |

**On the false-alarm rate specifically:** we hold any proposed improvement to a strict bar before shipping it — it must not decrease overall accuracy, must not decrease binary accuracy, must improve the false-alarm rate, and must not cost any individual fault type more than 2 percentage points of detection recall, verified on data the change was never tuned against. Using this standard we have tested, and honestly rejected, three separate improvement attempts (an output-reweighting fix, an added-feature fix, and a decision-layer persistence fix) because each helped on some axis but cost too much elsewhere. We consider this rejection discipline part of the project's credibility, not a weakness to hide — the shipped model is the one that has survived every test thrown at it, not the one with the best-looking single number.

## Known Issues

- **Simulator + scenario dropdown:** changing the scenario selection while a simulation is already running breaks the frontend's polling loop — stations will stop receiving new samples and eventually show "Not Reporting," even though the backend is fine. Workaround: stop the simulation (or let it finish) before selecting a new scenario, then start again.
- **Global Brain LSTM warm-up:** after a station connects or restarts, the LSTM's reconstruction-based anomaly score needs 20 consecutive 60-second observations before it reports a calibrated confidence (shown as "Warming Up" with 0% confidence, by design — the system does not fabricate a confidence number during this period). The Local Edge MLP + rules and the spatial cross-check are both active immediately and are not affected by this warm-up.
- **False-alarm rate (~11%):** the main open area for improvement; see Evaluation section above.
- **ESP32 hardware field validation:** all firmware logic is verified via native (PC-side) unit/parity tests; extended field testing on physical hardware is still outstanding.

## License / Credits

Built by **Super Tech Titans** for Smart India Hackathon 2026, Problem Statement SIH26073.
