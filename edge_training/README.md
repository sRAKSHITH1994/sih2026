# ESP32-S3 edge-ML training

The firmware contains a genuinely trained 56-input MLP. Features 48–55 are
explicit validity masks, allowing the same model to work with the current
BMP280 + MPU6050 + INA219 prototype and with optional instruments added later.

## Reproducible prototype model

```powershell
cd edge_training
python -m pip install -r requirements.txt
python train_edge_mlp.py
```

The script splits by complete sequence, trains the `56 → 24 → 12 → 10` MLP,
writes metrics under `artifacts/`, and exports
`firmware/include/model_weights.h` for ESP32 inference.

The bundled corpus is synthetic and is suitable for pipeline verification,
not field-accuracy claims. Use `collect_serial.py --port COM11` to collect real
prototype data, perform controlled fault experiments, and retrain before
reporting deployment accuracy.
