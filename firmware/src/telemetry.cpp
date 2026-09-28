#include "telemetry.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

#include "config.h"
#include "alarm_manager.h"
#include "lora_fallback.h"
#include "sensor_manager.h"
#include "station_position.h"

namespace {
struct QueueItem {
  char json[TELEMETRY_PAYLOAD_SIZE];
  char lora[220];
  uint32_t sequence;
  bool critical;
};
QueueHandle_t telemetryQueue = nullptr;
TaskHandle_t telemetryTaskHandle = nullptr;
constexpr uint32_t TELEMETRY_TASK_STACK_BYTES = 12 * 1024;
// QueueItem is a little over 4 KB. Keeping producer/consumer buffers in static
// storage prevents them from exhausting the Arduino and telemetry task stacks.
// Each buffer has ONE owner: loop() builds producerItem; worker() uses workerItem.
// FreeRTOS copies bytes into the queue, so queued records do not alias either.
QueueItem producerItem{};
QueueItem workerItem{};
String endpoint;
String localIp = "0.0.0.0";
volatile int lastHttpCode = 0;
volatile bool serverReachable = false;
unsigned long lastQueuedMs = 0;
uint32_t lastLoRaSequence = UINT32_MAX;

void addSensor(JsonObject sensors, const char *key, bool attached, bool valid, const char *type) {
  JsonObject node = sensors[key].to<JsonObject>();
  node["attached"] = attached;
  node["valid"] = valid;
  node["sensor_type"] = type;
  node["values"].to<JsonObject>();
}

void addAffectedSensors(JsonArray output, const char *csv) {
  char copy[96];
  strncpy(copy, csv, sizeof(copy) - 1);
  copy[sizeof(copy) - 1] = '\0';
  char *token = strtok(copy, ",");
  while (token != nullptr) {
    output.add(token);
    token = strtok(nullptr, ",");
  }
}

bool makePayload(const SensorSnapshot &snapshot, const LocalDecision &decision, QueueItem &item) {
  JsonDocument doc;
  doc["schema_version"] = "1.0";
  doc["station_id"] = STATION_ID;
  doc["station_name"] = STATION_NAME;
  doc["uptime_ms"] = snapshot.timestampMs;
  doc["sequence"] = snapshot.sequence;
  doc["latitude"] = STATION_LATITUDE;
  doc["longitude"] = STATION_LONGITUDE;
  doc["firmware_version"] = FIRMWARE_VERSION;
  doc["source_mode"] = "HARDWARE";

  JsonObject sensors = doc["sensors"].to<JsonObject>();
  addSensor(sensors, "bmp280", snapshot.status[SENSOR_BMP].attached, snapshot.status[SENSOR_BMP].valid, "BMP280");
  sensors["bmp280"]["values"]["temperature_c"] = snapshot.temperatureC;
  sensors["bmp280"]["values"]["pressure_hpa"] = snapshot.pressureHpa;
  addSensor(sensors, "humidity", snapshot.status[SENSOR_HUMIDITY].attached, snapshot.status[SENSOR_HUMIDITY].valid, humiditySensorName());
  sensors["humidity"]["values"]["humidity_pct"] = snapshot.humidityPct;
  addSensor(sensors, "mpu6050", snapshot.status[SENSOR_MPU].attached, snapshot.status[SENSOR_MPU].valid, "MPU6050");
  sensors["mpu6050"]["values"]["accel_x_ms2"] = snapshot.ax;
  sensors["mpu6050"]["values"]["accel_y_ms2"] = snapshot.ay;
  sensors["mpu6050"]["values"]["accel_z_ms2"] = snapshot.az;
  sensors["mpu6050"]["values"]["gyro_x_rads"] = snapshot.gx;
  sensors["mpu6050"]["values"]["gyro_y_rads"] = snapshot.gy;
  sensors["mpu6050"]["values"]["gyro_z_rads"] = snapshot.gz;
  addSensor(sensors, "ina219", snapshot.status[SENSOR_INA].attached, snapshot.status[SENSOR_INA].valid, "INA219");
  sensors["ina219"]["values"]["bus_voltage_v"] = snapshot.busVoltageV;
  sensors["ina219"]["values"]["current_ma"] = snapshot.currentMa;
  sensors["ina219"]["values"]["power_mw"] = snapshot.powerMw;
  addSensor(sensors, "rain", snapshot.status[SENSOR_RAIN].attached, snapshot.status[SENSOR_RAIN].valid, "TIPPING_BUCKET");
  sensors["rain"]["values"]["rain_rate_mm_h"] = snapshot.rainRateMmH;
  sensors["rain"]["values"]["rain_total_mm"] = snapshot.rainTotalMm;
  addSensor(sensors, "wind", snapshot.status[SENSOR_WIND].attached, snapshot.status[SENSOR_WIND].valid, "ANEMOMETER");
  sensors["wind"]["values"]["wind_speed_ms"] = snapshot.windSpeedMs;
  addSensor(sensors, "vane", snapshot.status[SENSOR_VANE].attached, snapshot.status[SENSOR_VANE].valid, "WIND_VANE");
  sensors["vane"]["values"]["wind_direction_deg"] = snapshot.windDirectionDeg;
  addSensor(sensors, "solar", snapshot.status[SENSOR_SOLAR].attached, snapshot.status[SENSOR_SOLAR].valid, "PYRANOMETER");
  sensors["solar"]["values"]["solar_wm2"] = snapshot.solarWm2;

  JsonObject local = doc["local_brain"].to<JsonObject>();
  local["anomaly"] = decision.anomaly;
  local["fault_type"] = decision.faultType;
  local["severity_score"] = decision.severityScore;
  local["severity_level"] = decision.severityLevel;
  local["confidence"] = decision.confidence;
  local["trust_score"] = decision.trustScore;
  local["explanation"] = decision.explanation;
  local["warmup_complete"] = decision.warmupComplete;
  local["ewma_score"] = decision.ewmaScore;
  local["cusum_score"] = decision.cusumScore;
  local["ml_valid"] = decision.mlValid;
  local["ml_class"] = decision.mlClass;
  local["ml_probability"] = decision.mlProbability;
  local["ml_class_name"] = decision.mlClassName;
  local["ml_top_features"] = decision.mlTopFeatures;
  local["failure_risk_score"] = decision.failureRiskScore;
  local["station_state"] = decision.stationState;
  local["maintenance_action"] = decision.maintenanceAction;
  local["pre_failure_warning"] = decision.preFailureWarning;
  local["alarm_state"] = alarmState();
  // MPU_POSITION_ADDITION: read on the loop task before the packet is queued.
  const auto& position = stationPositionReport();
  JsonObject pose = local["station_position"].to<JsonObject>();
  pose["state"] = position.state;
  pose["calibrated"] = position.calibrated;
  pose["calibrating"] = position.calibrating;
  pose["saved"] = stationPositionModelSaved();
  pose["sample_valid"] = position.sampleValid;
  pose["measurement_valid"] = position.measurementValid;
  pose["active"] = position.active;
  pose["critical"] = position.critical;
  if (position.measurementValid) pose["tilt_deg"] = position.tiltDeg;
  else pose["tilt_deg"] = nullptr;
  pose["tolerance_deg"] = position.toleranceDeg;
  pose["method"] = "calibrated_gravity_baseline";

  addAffectedSensors(local["affected_sensors"].to<JsonArray>(), decision.affectedSensors);
  JsonObject health = local["sensor_health"].to<JsonObject>();
  for (int i = 0; i < SENSOR_COUNT; ++i) health[sensorKey(static_cast<SensorId>(i))] = decision.health[i];
  JsonObject healthStates = local["sensor_health_state"].to<JsonObject>();
  for (int i = 0; i < SENSOR_COUNT; ++i) healthStates[sensorKey(static_cast<SensorId>(i))] = decision.healthState[i];
  JsonObject trusted = local["trusted_values"].to<JsonObject>();
  trusted["temperature_c"] = decision.trusted.values.temperatureC;
  trusted["pressure_hpa"] = decision.trusted.values.pressureHpa;
  trusted["humidity_pct"] = decision.trusted.values.humidityPct;
  trusted["any_estimated"] = decision.trusted.anyEstimated;
  JsonObject estimated = trusted["estimated"].to<JsonObject>();
  JsonObject ages = trusted["age_ms"].to<JsonObject>();
  for (int i = 0; i < SENSOR_COUNT; ++i) {
    estimated[sensorKey(static_cast<SensorId>(i))] = decision.trusted.estimated[i];
    ages[sensorKey(static_cast<SensorId>(i))] = decision.trusted.ageMs[i];
  }
  JsonObject recovery = local["recovery"].to<JsonObject>();
  recovery["attempted"] = decision.recovery.attempted;
  recovery["recovered"] = decision.recovery.recovered;
  recovery["sensor"] = sensorKey(decision.recovery.sensor);
  recovery["attempts"] = decision.recovery.attempts;
  recovery["domain"] = decision.recovery.domain;
  recovery["action"] = decision.recovery.action;

  JsonObject link = doc["link"].to<JsonObject>();
  link["type"] = "WIFI_PRIMARY";
  link["rssi_dbm"] = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  link["queue_depth"] = telemetryQueue == nullptr ? 0 : uxQueueMessagesWaiting(telemetryQueue);
  link["lora_enabled"] = ENABLE_LORA;
  link["lora_available"] = loraFallbackAvailable();
  item.sequence = snapshot.sequence;
  item.critical = decision.severityScore >= 75.0f || decision.preFailureWarning;
  snprintf(item.lora,sizeof(item.lora),"%s|%lu|%s|%.0f|%.2f|%.0f|%s",STATION_ID,snapshot.sequence,
           decision.faultType,decision.severityScore,decision.confidence,decision.failureRiskScore,decision.stationState);
  const size_t length = serializeJson(doc, item.json, sizeof(item.json));
  return length > 0 && length < sizeof(item.json) - 1;
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  serverReachable = false;
  WiFi.disconnect();
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
  const unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < WIFI_RETRY_MS) {
    delay(250);
    Serial.print('.');
  }
  if (WiFi.status() == WL_CONNECTED) {
    localIp = WiFi.localIP().toString();
    Serial.printf(" connected, IP=%s, RSSI=%d dBm\n", localIp.c_str(), WiFi.RSSI());
  } else {
    Serial.println(" retry scheduled");
  }
}

void worker(void *) {
  for (;;) {
    ensureWifi();
    if (WiFi.status() != WL_CONNECTED && telemetryQueue &&
        xQueuePeek(telemetryQueue, &workerItem, 0) == pdTRUE && workerItem.critical &&
        workerItem.sequence != lastLoRaSequence && loraFallbackAvailable()) {
      if (loraSendPayload(workerItem.lora)) {
        lastLoRaSequence = workerItem.sequence;
        Serial.printf("[LORA] critical fallback sent for sequence %lu\n", (unsigned long)workerItem.sequence);
      }
    }
    if (WiFi.status() == WL_CONNECTED && telemetryQueue && xQueuePeek(telemetryQueue, &workerItem, pdMS_TO_TICKS(300)) == pdTRUE) {
      WiFiClient client;
      HTTPClient http;
      http.setTimeout(HTTP_TIMEOUT_MS);
      http.begin(client, endpoint);
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-Station-Token", STATION_TOKEN);
      const int code = http.POST(reinterpret_cast<uint8_t *>(workerItem.json), strlen(workerItem.json));
      lastHttpCode = code;
      serverReachable = code >= 200 && code < 300;
      if (serverReachable) {
        // Reuse the static worker buffer instead of allocating a second 4 KB
        // QueueItem on the task stack.
        xQueueReceive(telemetryQueue, &workerItem, 0);  // Remove only after server acceptance.
      } else {
        Serial.printf("[HTTP] send failed code=%d, retaining %u queued packet(s)\n", code, uxQueueMessagesWaiting(telemetryQueue));
        if (workerItem.critical && workerItem.sequence != lastLoRaSequence && loraFallbackAvailable() && loraSendPayload(workerItem.lora)) {
          lastLoRaSequence = workerItem.sequence;
        }
      }
      http.end();
    }
    vTaskDelay(pdMS_TO_TICKS(500));
  }
}
}  // namespace

void telemetryBegin() {
  if (telemetryQueue != nullptr) return;  // Never start a second buffer owner.
  endpoint = String("http://") + DASHBOARD_HOST + ":" + DASHBOARD_PORT + "/api/v1/telemetry";
  telemetryQueue = xQueueCreate(TELEMETRY_QUEUE_SIZE, sizeof(QueueItem));
  loraFallbackBegin();
  Serial.printf("[TELEMETRY] Wi-Fi endpoint: %s\n", endpoint.c_str());
  if (telemetryQueue == nullptr) {
    Serial.println("[TELEMETRY] ERROR: queue allocation failed");
    return;
  }
  const BaseType_t created = xTaskCreatePinnedToCore(worker, "wifi-telemetry", TELEMETRY_TASK_STACK_BYTES, nullptr, 1, &telemetryTaskHandle, 0);
  if (created != pdPASS) {
    // Do not keep filling a queue with no consumer if task allocation fails.
    vQueueDelete(telemetryQueue);
    telemetryQueue = nullptr;
    telemetryTaskHandle = nullptr;
    Serial.println("[TELEMETRY] ERROR: Wi-Fi task creation failed; local monitoring continues");
    return;
  }
  Serial.printf("[TELEMETRY] Wi-Fi worker started (stack=%lu bytes)\n", (unsigned long)TELEMETRY_TASK_STACK_BYTES);
}

void telemetryUpdate(const SensorSnapshot &snapshot, const LocalDecision &decision) {
  const unsigned long interval = decision.anomaly ? ALERT_TELEMETRY_INTERVAL_MS : TELEMETRY_INTERVAL_MS;
  if (millis() - lastQueuedMs < interval || telemetryQueue == nullptr) return;
  lastQueuedMs = millis();
  if (!makePayload(snapshot, decision, producerItem)) {
    Serial.println("[TELEMETRY] JSON payload overflow; packet not queued");
    return;
  }
  if (xQueueSend(telemetryQueue, &producerItem, 0) != pdTRUE) {
    Serial.println("[TELEMETRY] Queue full; newest sample skipped and stored packets preserved");
  }
}

bool telemetryWifiConnected() { return WiFi.status() == WL_CONNECTED; }
bool telemetryServerReachable() { return serverReachable; }
int telemetryQueueDepth() { return telemetryQueue ? uxQueueMessagesWaiting(telemetryQueue) : 0; }
int telemetryLastHttpCode() { return lastHttpCode; }
const char *telemetryLocalIp() { return localIp.c_str(); }
const char *telemetryUrl() { return endpoint.c_str(); }
