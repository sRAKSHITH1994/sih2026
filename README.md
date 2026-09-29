# SIH26073 Final System — Local Brain + Global Brain

Version 3 is the complete Wi-Fi-first SIH prototype for anomaly-aware automatic weather stations. Start with [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md) if you are new to VS Code or ESP32.

## What is actually implemented

- **ESP32-S3 Local Brain:** 20-sample temporal window, 56 features, a trained 56→24→12→10 MLP, explicit missing-sensor masks, EWMA, CUSUM, strengthened rules, evidence fusion, health/trust scoring, explainable top features, trusted last-good fallback with age, targeted recovery, and store-and-forward.
- **“Warning before station dies”:** INA219 supply trends, Wi-Fi/queue condition, sensor health and anomaly evidence generate a failure-risk score and maintenance advice before total shutdown.
- **Local alarm:** green/yellow/red LEDs and buzzer work even when the laptop or Wi-Fi is unavailable.
- **Global Brain:** trained 20-sample **T/P LSTM** when humidity is absent and a trained **T/P/H LSTM** when external humidity is attached, plus robust optional-sensor monitoring, physical consistency, exact Shapley feature attribution, and source-isolated spatial verification.
- **Dashboard:** Live Intelligence, Evaluation Criteria, Hardware Integration, and Station Simulator pages.
- **Transport:** authenticated Wi-Fi/HTTP is primary. SX127x LoRa is an optional compact critical-alert fallback and requires a separate receiving gateway.
- **Scientific boundaries:** absent sensors produce no fake values; simulation never corroborates hardware; one real station cannot invent neighbours; included metrics are synthetic/injected, not field certification.

## Hardware defaults

| Device | Purpose | Default |
|---|---|---|
| ESP32-S3 DevKitC-1 N8 | Local Brain and communications | Enabled |
| BMP280-compatible module | Temperature and pressure only | Enabled |
| MPU6050 | Movement, impact, tilt | Enabled |
| INA219 | Supply voltage, current, power | Enabled |
| SHT31 or DHT22 | External humidity | DHT11 attached |
| Rain, anemometer, wind vane, pyranometer | Expansion instruments | Not attached |
| SX127x LoRa | Critical-alert fallback | Disabled |

The BME-labelled board is deliberately handled as a BMP280. Its humidity field is never used. When an external humidity sensor is later wired and enabled, its validity mask, Local Brain features, telemetry, dashboard and T/P/H Global model activate automatically.

## Run the dashboard

On Windows, double-click `start_dashboard.bat`. The launcher finds the `.venv` either inside this project or beside it. It installs requirements only once, then later starts go directly to the server. Keep its window open and visit `http://127.0.0.1:8000`.

Linux/macOS:

```bash
chmod +x start_dashboard.sh
./start_dashboard.sh
```

## Configure and upload firmware

Edit `firmware/include/user_config.h`:

```cpp
#define WIFI_SSID "YOUR_2_4_GHZ_WIFI"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define DASHBOARD_HOST "192.168.67.159"
```

Then open the `firmware` folder in VS Code with PlatformIO, build, upload, and open Serial Monitor at 115200 baud. Full beginner steps and upload troubleshooting are in [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md).

## How the models handle the current prototype

- The edge MLP always receives 56 entries. Features 48–55 are validity masks, so “not attached” is different from a genuine zero.
- Training contains core-only, core+humidity, partial expansion, and full expansion profiles.
- With current hardware, BMP280 + MPU6050 + INA219 are processed while humidity/rain/wind/vane/solar masks remain zero.
- When a sensor is enabled and produces valid values, it enters the Local Brain and Global adaptive monitor without manufacturing old readings.
- The Global Brain uses T/P today; it changes to T/P/H only after 20 valid external-humidity samples.

## Evaluation and honest accuracy

Two separate model artifacts are included:

- Edge MLP grouped-sequence held-out test: about **90.1% accuracy**, **89.8% balanced accuracy**, **88.9% macro F1** on generated fault-profile data.
- Global pipeline: rerun `python scripts/run_evaluation.py` or use the Evaluation page for exact current injected-data metrics.

These results validate software behavior under documented injection. They do **not** replace real sensor calibration, real weather comparison, physical fault trials, or long-duration field metrics. Use `edge_training/collect_serial.py` to build real deployment data, then retrain the edge model.

## Key paths

- `firmware/` — complete ESP32-S3 Local Brain
- `edge_training/` — data collection, 56-feature pipeline, training/export, metrics
- `backend/app/` — FastAPI Global Brain, dual LSTM, XAI, simulator, storage
- `frontend/` — React dashboard and included production build
- `docs/ARCHITECTURE.md` — complete processing architecture
- `docs/HARDWARE_CONNECTIONS.md` — current and optional wiring
- `docs/EVALUATION.md` — test protocol and claim limits

## Developer verification

```bash
python -m pytest -q
python scripts/run_evaluation.py
cd frontend && npm ci && npm run build
cd ../firmware && pio run
```

PlatformIO downloads the pinned ESP32 platform and libraries on its first build.

further changes will be made.
