# Hardware connections

## Present I²C modules

Use 3.3 V logic and connect every ground together.

| ESP32-S3 | BMP280 | MPU6050 | INA219 | Optional SHT31 |
|---|---|---|---|---|
| 3V3 | VCC | VCC | VCC | VCC |
| GND | GND | GND | GND | GND |
| GPIO 8 | SDA | SDA | SDA | SDA |
| GPIO 9 | SCL | SCL | SCL | SCL |

Expected addresses: BMP280 `0x76/0x77`, MPU6050 `0x68/0x69`, INA219 `0x40`, SHT31 `0x44`.

Route the monitored positive supply through the INA219 shunt: supply positive → `VIN+`, `VIN-` → load positive. Do not route ground through the shunt. Confirm your breakout's limits.

## Local warning devices

| Output | ESP32-S3 connection | Behavior |
|---|---|---|
| Green LED | GPIO 2 → 220–330 Ω → LED anode; cathode → GND | Normal |
| Yellow LED | GPIO 3 → 220–330 Ω → LED anode; cathode → GND | Warning/degradation |
| Red LED | GPIO 11 → 220–330 Ω → LED anode; cathode → GND | Critical fault |
| Active buzzer/control | GPIO 12 | Pulses during critical alarm |

Use a transistor driver for a buzzer whose current exceeds the GPIO limit. Never power a high-current buzzer directly from a GPIO.

## External humidity—not attached now

Leave `ENABLE_EXTERNAL_HUMIDITY 0`. The dashboard correctly shows **Not attached** and the Global Brain uses its trained T/P model.

For SHT31, wire it on the shared I²C bus, then set:

```cpp
#define ENABLE_EXTERNAL_HUMIDITY 1
#define HUMIDITY_SENSOR_TYPE HUMIDITY_SHT31
```

For DHT22, connect VCC→3V3, GND→GND and DATA→GPIO 4; use a 4.7–10 kΩ pull-up from DATA to 3V3 if the module lacks one. Then select `HUMIDITY_DHT22`. Rebuild/upload after any macro change.

## Optional weather instruments

| Instrument | Pin | Enable macro | Required calibration |
|---|---:|---|---|
| Tipping-bucket rain gauge | GPIO 5 | `ENABLE_RAIN_GAUGE` | `RAIN_GAUGE_MM_PER_TIP`; rate uses a 60 s window |
| Cup anemometer | GPIO 6 | `ENABLE_ANEMOMETER` | `ANEMOMETER_MS_PER_HZ` |
| Wind vane | GPIO 7 ADC | `ENABLE_WIND_VANE` | ADC endpoints or calibrated LUT |
| Pyranometer | GPIO 10 ADC | `ENABLE_PYRANOMETER` | `PYRANOMETER_WM2_PER_COUNT` |

Passive pulse/analog instruments cannot be identified electronically. Enable one only after it is physically connected and calibrated. Until then its telemetry contains no reading and displays **Not attached**.

## Optional SX127x LoRa

Default is `ENABLE_LORA 0`. Example configured pins are SCK 18, MISO 17, MOSI 16, CS 15, RESET 14 and DIO0 13 at 433 MHz. Confirm the legal frequency for your location and exact module voltage. You also need a receiving LoRa gateway; the browser cannot receive LoRa directly.

## Wi-Fi checklist

- Laptop and ESP32 must use the same 2.4 GHz LAN.
- `DASHBOARD_HOST` defaults to `192.168.67.159`; update it if `ipconfig` shows a different laptop IPv4.
- Keep `start_dashboard.bat` running and allow private-network TCP port 8000.
- Avoid guest networks with client isolation.
- Keep the station token equal on firmware and backend.
