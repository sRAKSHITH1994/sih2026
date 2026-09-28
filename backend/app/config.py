from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DATA_DIR = BACKEND_ROOT / "data"
MODEL_DIR = BACKEND_ROOT / "models"
DB_PATH = Path(os.getenv("SIH_DB_PATH", DATA_DIR / "global_brain.db"))
MODEL_TPH_PATH = Path(os.getenv("SIH_LSTM_TPH_MODEL", MODEL_DIR / "lstm_tph_autoencoder.npz"))
MODEL_TP_PATH = Path(os.getenv("SIH_LSTM_TP_MODEL", MODEL_DIR / "lstm_tp_autoencoder.npz"))
# Backwards-compatible alias used by evaluation and tests.
MODEL_PATH = MODEL_TPH_PATH

STATION_TOKEN = os.getenv("SIH_STATION_TOKEN", "sih26073-demo-token")
STALE_SECONDS = int(os.getenv("SIH_STALE_SECONDS", "20"))
NEIGHBOR_MAX_AGE_SECONDS = int(os.getenv("SIH_NEIGHBOR_MAX_AGE_SECONDS", "120"))
MIN_SPATIAL_NEIGHBORS = int(os.getenv("SIH_MIN_SPATIAL_NEIGHBORS", "2"))
SPATIAL_RADIUS_KM = float(os.getenv("SIH_SPATIAL_RADIUS_KM", "100"))

CORE_FEATURES = ("temperature_c", "pressure_hpa", "humidity_pct")
CORE_TP_FEATURES = ("temperature_c", "pressure_hpa")

# Difference scales used to compare real neighbouring stations. These are not
# anomaly thresholds; they normalize different physical units before distance.
SPATIAL_SCALES = {
    "temperature_c": 3.0,
    "pressure_hpa": 4.0,
    "humidity_pct": 10.0,
    "wind_speed_ms": 3.0,
    "rain_rate_mm_h": 15.0,
    "solar_wm2": 250.0,
}
