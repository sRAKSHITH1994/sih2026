# Add station-position detection to your existing project

This is an addition package for the SIH26073 FINAL SYSTEM 3.0/3.0.1 source layout.
It is not a replacement project. The installer checks the existing code before
editing it, backs up changed files, and leaves Wi-Fi credentials, sensor settings,
DHT11 edits, model weights and the telemetry crash fix intact.

## What your current firmware does

The existing edge MLP receives acceleration magnitude, its standard deviation,
its change and gyroscope magnitude. Its MECHANICAL class and rule can detect
disturbance, but there is no saved reference orientation. Once the station lies
still on its side, acceleration magnitude can still be approximately 9.81 m/s²
and the gyro can return near zero. The old detector can therefore miss sustained
displacement after movement stops.

## What this addition does

- Fits a normal gravity direction and angular-noise tolerance from 30 stationary
  samples after you explicitly send `MPUCAL`.
- Uses all three accelerometer axes; the MPU may be installed in any fixed
  orientation. Its intended mounted pose becomes the reference.
- Saves that reference in ESP32 NVS flash. Resetting a fallen station does not
  automatically teach it that the fallen pose is normal.
- Detects persistent tilt independently of the weather MLP's 20-sample warm-up.
- Keeps the position alarm until the station is back close to its reference
  pose with stable, valid measurements for five seconds.
- Sends the position state, angle, tolerance and alert to the existing dashboard.
- Identifies physical mounting faults without treating a working MPU as a
  defective sensor. Independent MPU read failures still count as data loss.

This is a calibrated statistical detector alongside your existing trained MLP.
It learns a baseline and variation, but it does not retrain the neural network.
Its 0.90/0.95 alert confidence values are heuristic evidence scores, not measured
accuracy or calibrated failure probabilities. Its demo thresholds need testing
on your mounted station.

## 1. Put this folder in the existing project

Download and extract `SIH26073_MPU_POSITION_ADDITION.zip` using Windows
"Extract All". Place the extracted `SIH26073_MPU_POSITION_ADDITION` folder inside:

```
C:\sih2026\SIH26073_LocalBrain\SIH26073_FINAL_LOGOB_pro\SIH26073_FINAL_SYSTEM
```

That directory already contains `backend`, `firmware`, and `start_dashboard.bat`.
The addition folder should sit beside those folders. Inside the addition folder
you must see `apply_addition.py`, `START_HERE.md`, `files`, and `tests`.

Do not replace your existing project folder. Do not paste individual files over
your Wi-Fi configuration or your DHT11 sensor-manager changes.

## 2. Apply the small edits

1. In VS Code, stop the running dashboard terminal with Ctrl+C.
2. Close the PlatformIO Serial Monitor so COM11 is free.
3. Select Terminal > New Terminal.
4. Paste this command and press Enter:

```powershell
cd "C:\sih2026\SIH26073_LocalBrain\SIH26073_FINAL_LOGOB_pro\SIH26073_FINAL_SYSTEM"
```

5. Paste this command and press Enter:

```powershell
python .\SIH26073_MPU_POSITION_ADDITION\apply_addition.py --project .
```

The successful message is:

```
MPU position addition installed.
Original files backed up at: ...\mpu_position_backups\...
Next: restart the dashboard, build/upload firmware, then calibrate using MPUCAL.
```

It needs only Python's built-in modules. Running it again is safe: it reports
that the addition is already installed. If it prints STOP because your current
files differ from the expected version, it makes no changes. Send the error and
the named file; do not force replacements.

## 3. Build and upload

1. Disconnect the external 5 V station supply before attaching ESP USB. The
   external INA219 station-power arrangement and ordinary USB power must not
   be connected simultaneously.
2. Connect ESP USB to your laptop.
3. Open your existing `firmware` folder/project in PlatformIO.
4. In PlatformIO > Project Tasks > esp32-s3-devkitc-1-n8 > General, click Build.
5. After Build succeeds, click Upload. Keep the Serial Monitor closed during
   Upload.
6. Open Monitor. It remains at 115200 baud. The installer removes the unsupported
   `colorize` filter and adds `send_on_enter` so you can type commands.

No new Arduino library needs to be installed: Preferences comes with the ESP32
Arduino framework already used by this project.

## 4. Check MPU readings before calibration

Rigidly attach the MPU6050 to the demo station itself. It must move with the
station, not sit loose beside it. Put the complete station in its intended
upright position.

Your existing I2C wiring is:

| MPU6050 connection | ESP32-S3 |
| --- | --- |
| Supply suitable for your breakout's 3.3 V operation | 3V3 |
| GND | GND |
| SDA | GPIO8 |
| SCL | GPIO9 |

These SDA/SCL wires can share the bus with your BMP280 and INA219.

Press RESET once, with BOOT released. Look for `MPU6050 OK 0x68` or
`MPU6050 OK 0x69` in the startup line. Its six readings must be numbers, not
`nan`. If the MPU still says FAIL/MPU_INVALID, repair that connection first;
calibration cannot work without valid data.

## 5. Teach the correct position once

1. Keep the station fixed in its intended position.
2. Click inside the Serial Monitor terminal.
3. Type `MPUCAL` in uppercase and press Enter.
4. Expect `[POSITION] Calibration started...`.
5. Do not move the station for approximately 30 seconds (30 valid, stationary
   samples at the existing one-second sampling interval).
6. Wait for `[POSITION] CALIBRATION SAVED...` and `saved=YES`.

You can send `MPUSTATUS` and press Enter to see the state. Typical output after
successful calibration is:

```
[POSITION] IN_POSITION | tilt=0.2deg tolerance=10.0deg | calibration=30/30 | saved=YES | alert=NO
```

Small noise is expected. The MPU provides six measurements, not one perfectly
constant number. Stable readings are normal for a stationary station.

Movement or invalid readings restart the continuous calibration sample count.
An unsuccessful attempt ends after 90 seconds; correct the cause and send
MPUCAL again. If SAVE FAILED appears, the new model is only in RAM: do not treat
it as protected across resets. Report that message before relying on it.

Do not send MPUCAL when the station is in the fallen position. Send it again
only after intentionally choosing or changing the correct physical mounting.

## 6. Restart the dashboard and test gently

Open another VS Code terminal in `SIH26073_FINAL_SYSTEM` and start the dashboard
using your existing working method, for example:

```powershell
.\start_dashboard.bat
```

Open `http://localhost:8000` on the laptop and select your real station. The
existing live fault headline and explanation show the mounting alert; no
frontend rebuild is needed. The complete structured position evidence is also
included in the saved telemetry and API response.

| Test | Position-detector result |
| --- | --- |
| Keep near the saved pose, with small noise/wobble | No position alarm |
| Hold roughly 15–20 degrees away for at least 3 seconds after settling | STATION_TILTED, HIGH, yellow LED if no more serious fault |
| Gently lay the station on its side, above 35 degrees, and hold still at least 3 seconds | STATION_FALLEN, CRITICAL, red LED and existing buzzer alarm |
| Leave it lying still | Position alarm stays active |
| Reset while it is lying down | Saved baseline loads; alarm returns after fresh confirmation |
| Return within approximately 6 degrees for at least 5 seconds | Position alarm clears |
| MPU becomes invalid during an active alarm | Alarm stays active; tilt is reported unavailable |

Do not physically drop the station. Tilt it by hand so the wiring is not pulled
out. Timing starts with valid settled samples. The current one-second acquisition
can miss brief impacts or a rapid fall-and-return; this addition detects sustained
orientation displacement, not a guaranteed pre-impact warning.

Other faults remain meaningful. For example, an unresolved INA219 ELECTRICAL
alarm can keep the red LED on after the position alarm clears. Look at the
`[POSITION]` line to test this addition independently.

When changing from USB programming power to the external INA219 5 V arrangement,
disconnect USB first. The calibration stays saved. View readings through Wi-Fi.

## Where the additions go

| File | Change |
| --- | --- |
| firmware/include/station_position_core.h | New baseline fitting, tolerance and persistent tilt logic |
| firmware/include/station_position.h | New interface |
| firmware/src/station_position.cpp | New serial calibration, flash persistence and decision integration |
| firmware/src/main.cpp | Include and three hook calls: begin, serial polling, position update |
| firmware/src/telemetry.cpp | Include and one station_position JSON block |
| firmware/src/health_engine.cpp | MECHANICAL class does not itself penalize MPU sensor health |
| firmware/include/config.h | Telemetry buffer increased to at least 5120 bytes for position metadata |
| firmware/platformio.ini | Supported monitor filters and command entry |
| backend/app/schemas.py | Preserve position metadata when parsing telemetry |
| backend/app/global_brain.py | Classify physical mounting faults before weather/spatial branches |

The exact code replacements are in `apply_addition.py`. It applies only these
edits and backs up the seven existing files before changing them. Your
user_config.h, sensor_manager.cpp, model files and database are not rewritten.

## Change tolerance later

Open `firmware/include/station_position_core.h`. The settings at the top are:

```cpp
constexpr unsigned CalibrationSamples = 30;
constexpr float MinimumToleranceDeg = 10.0f;
constexpr float MaximumToleranceDeg = 15.0f;
constexpr float FallenThresholdDeg = 35.0f;
constexpr uint32_t ConfirmationMs = 3000;
constexpr uint32_t RecoveryMs = 5000;
```

The learned alarm tolerance is the larger of MinimumToleranceDeg and the
calibration mean angular error plus six standard deviations. Calibration is
rejected if that needs more than MaximumToleranceDeg. Recovery uses 60% of the
learned tolerance. Rebuild/upload and run MPUCAL after changing thresholds.
Keep fall threshold higher than the normal tilt tolerance.

## Limits and validation

This detects tilt relative to gravity. It cannot establish geographic location,
detect a station moved sideways without changing its final orientation, or
reliably detect a pure rotation about the vertical axis. It does not prove that
every other sensor is accurate merely because it is reporting valid values.

Verified here using host C++ tests (including address/undefined-behavior
sanitizers), simulated ESP/Preferences interfaces, backend schema/classification
and database tests, and firmware C++ syntax checks with ESP API stubs. Tests
cover constant readings, noise, arbitrary mounting, slow tilt, a still fallen
station, reboot, invalid data, recovery, gaps, timer wraparound, serial input,
flash write failure, alarm output, and dashboard classification.

The patch installer was checked for compatibility and repeat execution.
An ESP32 target-toolchain build and physical hardware test were not available
here. Your Build, Upload and controlled tilt checks are required before judging
field reliability or claiming accuracy.

Technical references:
- Analog Devices, gravity-vector inclination sensing:
  https://www.analog.com/en/resources/app-notes/an-1057.html
- Espressif, Preferences/NVS persistence:
  https://docs.espressif.com/projects/arduino-esp32/en/latest/api/preferences.html

Data-storage answer: Yes.
