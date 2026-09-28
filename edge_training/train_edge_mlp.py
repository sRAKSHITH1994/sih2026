"""Train, evaluate and export the Local Brain MLP.

The included data generator is a reproducible engineering smoke-test corpus.
For final field claims, replace it with logged station sequences collected by
collect_serial.py and keep the same group-wise train/validation/test split.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from feature_pipeline import CLASS_NAMES, FEATURE_NAMES, WINDOW_SIZE, extract_sequence


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
OUTPUT = ROOT / "artifacts"
MODEL_HEADER = PROJECT / "firmware" / "include" / "model_weights.h"
RNG_SEED = 26073
SAMPLES = 150
ONSET = 70


def base_sequence(rng: np.random.Generator, profile: str) -> pd.DataFrame:
    k = np.arange(SAMPLES)
    phase = rng.uniform(0, np.pi)
    temperature = 28 + 2.8 * np.sin(k / 70 + phase) + rng.normal(0, 0.06, SAMPLES)
    pressure = 1008 + 0.9 * np.cos(k / 55 + phase / 2) + rng.normal(0, 0.08, SAMPLES)
    humidity = 68 - 8 * np.sin(k / 70 + phase) + rng.normal(0, 0.20, SAMPLES)
    ax = rng.normal(0, 0.015, SAMPLES); ay = rng.normal(0, 0.015, SAMPLES)
    az = 9.81 + rng.normal(0, 0.025, SAMPLES)
    gx = rng.normal(0, 0.003, SAMPLES); gy = rng.normal(0, 0.003, SAMPLES); gz = rng.normal(0, 0.003, SAMPLES)
    voltage = 5.05 + rng.normal(0, 0.012, SAMPLES)
    current = 105 + 4 * np.sin(k / 18) + rng.normal(0, 1.2, SAMPLES)
    power = voltage * current
    wind = np.clip(rng.normal(3.0, 0.7, SAMPLES), 0.05, None)
    vane = (rng.uniform(0, 360) + np.cumsum(rng.normal(0, 3.0, SAMPLES))) % 360
    rain = np.zeros(SAMPLES)
    solar = np.clip(700 + 180 * np.sin(k / 60) + rng.normal(0, 8, SAMPLES), 0, 1500)

    masks = {key: np.ones(SAMPLES, dtype=float) for key in ("bmp", "humidity", "mpu", "ina", "rain", "wind", "vane", "solar")}
    if profile == "core":
        for key in ("humidity", "rain", "wind", "vane", "solar"): masks[key][:] = 0
    elif profile == "core_humidity":
        for key in ("rain", "wind", "vane", "solar"): masks[key][:] = 0
    elif profile == "wind":
        for key in ("rain", "solar"): masks[key][:] = 0
    elif profile == "rain":
        for key in ("wind", "vane", "solar"): masks[key][:] = 0

    values = {
        "temperature_c": temperature, "pressure_hpa": pressure, "humidity_pct": humidity,
        "ax": ax, "ay": ay, "az": az, "gx": gx, "gy": gy, "gz": gz,
        "bus_voltage_v": voltage, "current_ma": current, "power_mw": power,
        "wind_speed_ms": wind, "wind_direction_deg": vane, "rain_rate_mm_h": rain, "solar_wm2": solar,
    }
    sensor_columns = {
        "humidity_pct": "humidity", "ax": "mpu", "ay": "mpu", "az": "mpu", "gx": "mpu", "gy": "mpu", "gz": "mpu",
        "bus_voltage_v": "ina", "current_ma": "ina", "power_mw": "ina", "wind_speed_ms": "wind",
        "wind_direction_deg": "vane", "rain_rate_mm_h": "rain", "solar_wm2": "solar",
    }
    for column, key in sensor_columns.items():
        values[column] = values[column] * masks[key]
    frame = pd.DataFrame(values)
    for key, value in masks.items(): frame[f"{key}_valid"] = value
    return frame


def inject(frame: pd.DataFrame, class_id: int, rng: np.random.Generator) -> None:
    n = len(frame) - ONSET
    if class_id == 1:
        frame.loc[ONSET, rng.choice(["temperature_c", "pressure_hpa", "humidity_pct"])] += rng.choice([-1, 1]) * rng.uniform(9, 15)
    elif class_id == 2:
        frame.loc[ONSET:, "temperature_c"] += np.linspace(0, 5, n)
        frame.loc[ONSET:, "pressure_hpa"] += np.linspace(0, 7, n)
        if frame.humidity_valid.iloc[0]: frame.loc[ONSET:, "humidity_pct"] += np.linspace(0, 15, n)
    elif class_id == 3:
        for column in ("temperature_c", "pressure_hpa"):
            frame.loc[ONSET:, column] = float(frame.loc[ONSET, column])
        if frame.humidity_valid.iloc[0]: frame.loc[ONSET:, "humidity_pct"] = float(frame.loc[ONSET, "humidity_pct"])
    elif class_id == 4:
        frame.loc[ONSET:, "temperature_c"] += rng.normal(0, 2.5, n)
        frame.loc[ONSET:, "pressure_hpa"] += rng.normal(0, 4.5, n)
        if frame.humidity_valid.iloc[0]: frame.loc[ONSET:, "humidity_pct"] += rng.normal(0, 9, n)
    elif class_id == 5:
        frame.loc[ONSET:, "bus_voltage_v"] -= np.linspace(0, 1.6, n)
        frame.loc[ONSET:, "current_ma"] += np.linspace(0, 180, n) + rng.normal(0, 5, n)
        frame.loc[ONSET:, "power_mw"] = frame.loc[ONSET:, "bus_voltage_v"] * frame.loc[ONSET:, "current_ma"]
    elif class_id == 6:
        frame.loc[ONSET:, "az"] += rng.normal(0, 2.2, n)
        frame.loc[ONSET:, "gx"] += rng.normal(0, 1.0, n)
    elif class_id == 7:
        frame.loc[ONSET:, "rain_rate_mm_h"] = 0
        frame.loc[ONSET:, "humidity_pct"] = np.clip(frame.loc[ONSET:, "humidity_pct"] + 25, 0, 100)
        frame.loc[ONSET:, "pressure_hpa"] -= np.linspace(0, 2.5, n)
    elif class_id == 8:
        frame.loc[ONSET:, "wind_speed_ms"] = 0
    elif class_id == 9:
        frame.loc[ONSET:, "wind_direction_deg"] = float(frame.loc[ONSET, "wind_direction_deg"])
        frame.loc[ONSET:, "wind_speed_ms"] = np.maximum(frame.loc[ONSET:, "wind_speed_ms"], 2.0)


def profile_for_class(class_id: int, repetition: int) -> str:
    if class_id == 7: return "rain"
    if class_id in (8, 9): return "wind"
    profiles = ("core", "core_humidity", "full", "core")
    return profiles[repetition % len(profiles)]


def make_dataset(repetitions: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for class_id, class_name in enumerate(CLASS_NAMES):
        for repetition in range(repetitions):
            profile = profile_for_class(class_id, repetition)
            frame = base_sequence(rng, profile)
            if class_id: inject(frame, class_id, rng)
            features = extract_sequence(frame)
            for index in range(WINDOW_SIZE - 1, len(frame)):
                label = class_id if class_id and index >= ONSET else 0
                rows.append({**dict(zip(FEATURE_NAMES, features[index])), "label": label,
                             "sequence_id": f"{class_name}_{profile}_{repetition:03d}", "sample_index": index,
                             "profile": profile, "fault_onset": ONSET if class_id else -1})
    return pd.DataFrame(rows)


def split_groups(frame: pd.DataFrame, seed: int):
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=seed)
    train_index, remaining_index = next(splitter.split(frame, groups=frame.sequence_id))
    train = frame.iloc[train_index].copy(); remaining = frame.iloc[remaining_index].copy()
    splitter2 = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=seed + 1)
    validation_index, test_index = next(splitter2.split(remaining, groups=remaining.sequence_id))
    return train, remaining.iloc[validation_index].copy(), remaining.iloc[test_index].copy()


def balance_training(frame: pd.DataFrame, seed: int) -> pd.DataFrame:
    counts = frame.label.value_counts()
    target = min(int(counts.max()), max(900, int(counts[counts.index != 0].median())))
    pieces = []
    for label, group in frame.groupby("label"):
        pieces.append(group.sample(n=min(len(group), target), random_state=seed + int(label)))
    return pd.concat(pieces).sample(frac=1, random_state=seed).reset_index(drop=True)


def _clean(array: np.ndarray) -> np.ndarray:
    result = np.asarray(array, dtype=np.float64).copy()
    result[np.abs(result) < 1e-30] = 0.0
    return result


def _numbers(array: np.ndarray) -> str:
    return ", ".join(f"{float(value):.9e}f" for value in _clean(array).reshape(-1))


def export_header(model: MLPClassifier, scaler: StandardScaler) -> None:
    first, second, third = model.coefs_
    bias1, bias2, bias3 = model.intercepts_
    standard = np.where(scaler.scale_ == 0, 1.0, scaler.scale_)
    lines = [
        "#ifndef MODEL_WEIGHTS_H", "#define MODEL_WEIGHTS_H", "",
        "// AUTO-GENERATED by edge_training/train_edge_mlp.py.",
        "// 56 inputs with explicit sensor-valid masks -> Dense(24) -> Dense(12) -> 10-class softmax.",
        f"static const float INPUT_MEAN[56] = {{{_numbers(scaler.mean_)}}};",
        f"static const float INPUT_STD[56] = {{{_numbers(standard)}}};", "",
    ]
    for name, weights in (("ML_W1", first), ("ML_W2", second), ("ML_W3", third)):
        lines.append(f"static const float {name}[{weights.shape[0]}][{weights.shape[1]}] = {{")
        lines.extend("    {" + _numbers(row) + "}," for row in _clean(weights))
        lines.extend(["};", ""])
    lines.extend([
        f"static const float ML_B1[24] = {{{_numbers(bias1)}}};",
        f"static const float ML_B2[12] = {{{_numbers(bias2)}}};",
        f"static const float ML_B3[10] = {{{_numbers(bias3)}}};", "", "#endif", "",
    ])
    MODEL_HEADER.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=28)
    parser.add_argument("--seed", type=int, default=RNG_SEED)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    dataset = make_dataset(args.repetitions, args.seed)
    train, validation, test = split_groups(dataset, args.seed)
    balanced_train = balance_training(train, args.seed)
    scaler = StandardScaler().fit(balanced_train[FEATURE_NAMES])
    classifier = MLPClassifier(hidden_layer_sizes=(24, 12), activation="relu", solver="adam", alpha=2e-4,
                               batch_size=128, learning_rate_init=8e-4, max_iter=260, random_state=args.seed,
                               early_stopping=True, validation_fraction=0.15, n_iter_no_change=18)
    classifier.fit(scaler.transform(balanced_train[FEATURE_NAMES]), balanced_train.label)

    metrics = {"architecture": [56, 24, 12, 10], "classes": CLASS_NAMES, "features": FEATURE_NAMES,
               "synthetic_training": True, "seed": args.seed, "window_size": WINDOW_SIZE,
               "split": "grouped by complete sequence: 70% train / 15% validation / 15% test"}
    for name, split in (("validation", validation), ("test", test)):
        prediction = classifier.predict(scaler.transform(split[FEATURE_NAMES]))
        metrics[name] = {
            "accuracy": float(accuracy_score(split.label, prediction)),
            "balanced_accuracy": float(balanced_accuracy_score(split.label, prediction)),
            "macro_f1": float(f1_score(split.label, prediction, average="macro")),
            "confusion_matrix": confusion_matrix(split.label, prediction, labels=range(len(CLASS_NAMES))).tolist(),
            "rows": int(len(split)), "sequences": int(split.sequence_id.nunique()),
        }
        print(name, classification_report(split.label, prediction, labels=range(len(CLASS_NAMES)), target_names=CLASS_NAMES, zero_division=0))

    joblib.dump(classifier, OUTPUT / "edge_mlp.joblib")
    joblib.dump(scaler, OUTPUT / "edge_scaler.joblib")
    dataset.sample(min(5000, len(dataset)), random_state=args.seed).to_csv(OUTPUT / "edge_training_sample.csv", index=False)
    (OUTPUT / "edge_mlp_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    export_header(classifier, scaler)
    print(json.dumps(metrics["test"], indent=2))
    print("Exported", MODEL_HEADER)


if __name__ == "__main__":
    main()

