"""Reference implementation of the ESP32-S3 Local Brain's 56 features.

The feature order and update equations mirror firmware/src/feature_engine.cpp.
Missing sensors are represented by zero-valued feature groups plus explicit
presence/validity masks (features 48..55).  The edge MLP is trained on several
hardware profiles, so an intentionally absent instrument never becomes a fake
zero reading or disables all local ML inference.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


WINDOW_SIZE = 20
EWMA_ALPHA = 0.10
BASELINE_ALPHA = 0.02
CUSUM_K = 0.45
CUSUM_LIMIT = 5.0
RAIN_MM_PER_TIP = 0.2794

SENSOR_KEYS = ("bmp", "humidity", "mpu", "ina", "rain", "wind", "vane", "solar")

FEATURE_NAMES = [
    "temperature", "temperature_delta", "temperature_std", "temperature_slope",
    "pressure", "pressure_delta", "pressure_std", "pressure_slope",
    "humidity", "humidity_delta", "humidity_std", "humidity_slope",
    "acceleration_norm", "acceleration_std", "acceleration_jerk", "gyro_norm",
    "bus_voltage", "bus_voltage_delta", "bus_voltage_std",
    "current_ma", "current_delta", "current_std", "power_mw", "power_slope",
    "ewma_temperature", "ewma_pressure", "ewma_humidity",
    "normalized_residual_temperature", "normalized_residual_pressure", "normalized_residual_humidity",
    "cusum_temperature", "cusum_pressure", "cusum_humidity",
    "wind_speed", "wind_speed_std", "wind_speed_slope", "wind_zero_fraction", "wind_gust_factor",
    "wind_direction_sin", "wind_direction_cos", "wind_direction_circular_variance", "wind_direction_stuck_fraction",
    "rain_rate", "rain_window_accumulation", "rain_humidity_inconsistency",
    "solar_irradiance", "solar_std", "solar_clear_ratio",
    "bmp_valid", "humidity_valid", "mpu_valid", "ina_valid",
    "rain_valid", "wind_valid", "vane_valid", "solar_valid",
]

CLASS_NAMES = [
    "NORMAL", "SPIKE", "DRIFT", "FROZEN", "ERRATIC", "ELECTRICAL",
    "MECHANICAL", "RAIN_BLOCKED", "WIND_SEIZED", "VANE_STUCK",
]

assert len(FEATURE_NAMES) == 56


def _std(values: np.ndarray) -> float:
    return float(np.std(values)) if len(values) else 0.0


def _slope(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=np.float64)
    denominator = len(values) * np.sum(x * x) - np.sum(x) ** 2
    if abs(denominator) < 1e-12:
        return 0.0
    return float((len(values) * np.sum(x * values) - np.sum(x) * np.sum(values)) / denominator)


def _angle_difference(a: float, b: float) -> float:
    difference = abs(a - b) % 360.0
    return 360.0 - difference if difference > 180.0 else difference


@dataclass
class ChannelState:
    ewma: float = 0.0
    baseline: float = 0.0
    positive: float = 0.0
    negative: float = 0.0
    initialized: bool = False

    def update(self, value: float, scale: float, valid: bool) -> tuple[float, float, float]:
        if not valid:
            return 0.0, 0.0, 0.0
        scale = max(scale, 1e-3)
        if not self.initialized:
            self.ewma = self.baseline = value
            self.initialized = True
            return self.ewma, 0.0, 0.0
        old_baseline = self.baseline
        self.ewma = EWMA_ALPHA * value + (1.0 - EWMA_ALPHA) * self.ewma
        normalized = (value - old_baseline) / scale
        self.positive = max(0.0, self.positive + normalized - CUSUM_K)
        self.negative = min(0.0, self.negative + normalized + CUSUM_K)
        if abs(normalized) <= 3.0:
            self.baseline = BASELINE_ALPHA * value + (1.0 - BASELINE_ALPHA) * old_baseline
        residual = (value - self.ewma) / scale
        signed_cusum = max(-4.0, min(4.0, (self.positive + self.negative) / CUSUM_LIMIT))
        return self.ewma, residual, signed_cusum


class FeatureExtractor:
    def __init__(self):
        self.history: list[dict[str, float]] = []
        self.temperature = ChannelState()
        self.pressure = ChannelState()
        self.humidity = ChannelState()
        self.solar_reference = 0.0

    def push(self, row: dict[str, float]) -> np.ndarray:
        self.history.append(row)
        self.history = self.history[-WINDOW_SIZE:]

        def series(name: str) -> np.ndarray:
            return np.asarray([float(item.get(name, 0.0)) for item in self.history], dtype=np.float64)

        t, p, h = series("temperature_c"), series("pressure_hpa"), series("humidity_pct")
        ax, ay, az = series("ax"), series("ay"), series("az")
        gx, gy, gz = series("gx"), series("gy"), series("gz")
        voltage, current, power = series("bus_voltage_v"), series("current_ma"), series("power_mw")
        wind, vane = series("wind_speed_ms"), series("wind_direction_deg")
        rain, solar = series("rain_rate_mm_h"), series("solar_wm2")

        acceleration = np.sqrt(ax * ax + ay * ay + az * az)
        gyro = np.sqrt(gx * gx + gy * gy + gz * gz)
        previous = lambda values: float(values[-2]) if len(values) > 1 else float(values[-1])
        jerk = float((acceleration[-1] - acceleration[-2]) - (acceleration[-2] - acceleration[-3])) if len(acceleration) >= 3 else 0.0

        t_ewma, t_residual, t_cusum = self.temperature.update(float(t[-1]), max(_std(t), 0.18), bool(row["bmp_valid"]))
        p_ewma, p_residual, p_cusum = self.pressure.update(float(p[-1]), max(_std(p), 0.35), bool(row["bmp_valid"]))
        h_ewma, h_residual, h_cusum = self.humidity.update(float(h[-1]), max(_std(h), 0.8), bool(row["humidity_valid"]))

        zero_fraction = float(np.mean(wind < 0.15)) if row["wind_valid"] else 0.0
        wind_mean = float(np.mean(wind))
        gust_factor = float(np.max(wind) / (wind_mean + 0.01)) if row["wind_valid"] else 0.0

        if row["vane_valid"]:
            radians = np.radians(vane)
            sine, cosine = float(np.sin(radians[-1])), float(np.cos(radians[-1]))
            resultant = math.hypot(float(np.mean(np.sin(radians))), float(np.mean(np.cos(radians))))
            circular_variance = 1.0 - resultant
            unchanged = sum(_angle_difference(float(vane[i]), float(vane[i - 1])) < 1.0 for i in range(1, len(vane)))
            stuck_fraction = unchanged / max(1, len(vane) - 1)
        else:
            sine = cosine = circular_variance = stuck_fraction = 0.0

        rain_accumulation = float(np.sum(rain) / 3600.0)
        rain_humidity_inconsistency = 0.0
        if row["rain_valid"] and rain[-1] > 0 and row["humidity_valid"]:
            rain_humidity_inconsistency = max(0.0, 80.0 - float(h[-1])) / 80.0

        if row["solar_valid"]:
            self.solar_reference = max(float(solar[-1]), self.solar_reference * 0.9995)
            clear_ratio = float(solar[-1]) / (self.solar_reference + 1.0)
        else:
            clear_ratio = 0.0

        features = [
            t[-1], t[-1] - previous(t), _std(t), _slope(t),
            p[-1], p[-1] - previous(p), _std(p), _slope(p),
            h[-1], h[-1] - previous(h), _std(h), _slope(h),
            acceleration[-1], _std(acceleration), jerk, gyro[-1],
            voltage[-1], voltage[-1] - previous(voltage), _std(voltage),
            current[-1], current[-1] - previous(current), _std(current), power[-1], _slope(power),
            t_ewma, p_ewma, h_ewma, t_residual, p_residual, h_residual,
            t_cusum, p_cusum, h_cusum,
            wind[-1], _std(wind), _slope(wind), zero_fraction, gust_factor,
            sine, cosine, circular_variance, stuck_fraction,
            rain[-1], rain_accumulation, rain_humidity_inconsistency,
            solar[-1], _std(solar), clear_ratio,
            *[float(row[f"{key}_valid"]) for key in SENSOR_KEYS],
        ]
        return np.asarray(features, dtype=np.float32)


def extract_sequence(frame: pd.DataFrame) -> np.ndarray:
    extractor = FeatureExtractor()
    return np.vstack([extractor.push(row) for row in frame.to_dict(orient="records")])

