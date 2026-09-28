# Start here — Windows beginner guide

Follow these steps in order. You do not need to type Python commands every time.

## A. Start the dashboard

1. Extract the ZIP completely. Do not run the project from inside the ZIP preview.
2. Open the extracted `SIH26073_FINAL_SYSTEM` folder.
3. Double-click `start_dashboard.bat`.
4. The first run may install Python packages. Later runs skip that installation.
5. Wait until the black window shows `Uvicorn running on http://0.0.0.0:8000`.
6. Keep the black window open.
7. Open Chrome or Edge and enter `http://127.0.0.1:8000`.
8. To stop, return to the black window and press `Ctrl+C` once.
9. To run it again later, double-click `start_dashboard.bat` again.

If Windows Firewall asks, allow access on **Private networks**. The ESP32 cannot send data while the server window is closed.

## B. Put your Wi-Fi details in the firmware

In VS Code, open `firmware/include/user_config.h`. Change only:

```cpp
#define WIFI_SSID "YOUR_2_4_GHZ_WIFI"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define DASHBOARD_HOST "192.168.67.159"
```

Use the same 2.4 GHz Wi-Fi on the laptop and ESP32. If your laptop's IPv4 changes, run `ipconfig` in Command Prompt and update `DASHBOARD_HOST`.

Humidity and the four weather instruments are intentionally disabled now. Leave their `ENABLE_...` values as `0` until they are physically wired.

## C. Install VS Code tools once

1. In VS Code, click the Extensions icon on the left.
2. Search for `PlatformIO IDE`.
3. Click **Install** and wait for it to finish.
4. Restart VS Code if it asks.
5. Click **File → Open Folder** and select the project's `firmware` folder—not the top folder.
6. Wait while PlatformIO downloads the ESP32 platform and sensor libraries. This can take several minutes the first time.

## D. Upload to ESP32-S3

1. Connect the ESP32-S3 using a USB **data** cable.
2. At the bottom of VS Code, click the ✓ icon to compile.
3. When compilation succeeds, click the → icon to upload.
4. If upload waits at `Connecting...`, hold the board's **BOOT** button, tap **RESET**, release **BOOT**, and try Upload again.
5. Click the plug/monitor icon at the bottom to open Serial Monitor at `115200` baud.
6. Press RESET once. Look for sensor detection, Wi-Fi connection, and HTTP `2xx` messages.

Now open the dashboard's **Live Intelligence** and **Hardware Integration** pages. BMP280, MPU6050 and INA219 should become Healthy. Humidity, rain, wind, vane and pyranometer should remain **Not attached**.

## E. Check the complete system without hardware

Open **Station Simulator**, select a scenario, and click **Start simulation**. The simulator uses the same telemetry contract and Global Brain path, but all records are clearly marked `SIMULATION` and never count as real-station evidence.

For the innovation demo, choose **Warning Before Station Dies**. After sample 25, voltage/current degradation raises the predicted failure risk, maintenance advice, yellow/red LED state and buzzer state.
