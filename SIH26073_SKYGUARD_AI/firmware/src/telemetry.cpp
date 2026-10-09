#include "telemetry.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <LittleFS.h>
#include <esp_partition.h>
#include <time.h>
#include <atomic>

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
QueueHandle_t criticalQueue = nullptr;
char bootId[40]{};
std::atomic<uint32_t> droppedPackets{0};std::atomic<int> durableDepth{0};std::atomic<bool> durableReady{false};
String durablePaths[96];int durableCount=0;uint32_t nextFile=0;
QueueItem dropItem{}; // producer-owned overflow scratch
QueueItem criticalItem{}; // worker-owned LoRa scratch
TaskHandle_t telemetryTaskHandle = nullptr;
constexpr uint32_t TELEMETRY_TASK_STACK_BYTES = 12 * 1024;
// QueueItem includes the JSON feature vector. Keeping these large buffers in static
// storage prevents them from exhausting the Arduino and telemetry task stacks.
// Each buffer has ONE owner: loop() builds producerItem; worker() uses workerItem.
// FreeRTOS copies bytes into the queue, so queued records do not alias either.
QueueItem producerItem{};
QueueItem workerItem{};
String endpoint;
char localIp[16]="0.0.0.0";
portMUX_TYPE ipMux=portMUX_INITIALIZER_UNLOCKED;
std::atomic<int> lastHttpCode{0};
std::atomic<bool> serverReachable{false};
unsigned long lastQueuedMs = 0;
uint32_t lastLoRaSequence = UINT32_MAX;
uint32_t lastCriticalAck = UINT32_MAX;

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
  doc["schema_version"] = "2.0";
  doc["boot_id"] = bootId;
  doc["captured_ms"] = snapshot.timestampMs;
  time_t now=time(nullptr)-uint32_t(millis()-snapshot.timestampMs)/1000;
  if(now>1700000000){struct tm utc;gmtime_r(&now,&utc);char stamp[32];strftime(stamp,sizeof(stamp),"%Y-%m-%dT%H:%M:%SZ",&utc);doc["timestamp"]=stamp;doc["time_quality"]="NTP";}
  else doc["time_quality"]="MONOTONIC_AGE";
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

  for(int i=0;i<SENSOR_COUNT;++i){sensors[sensorKey(static_cast<SensorId>(i))]["configured"]=snapshot.status[i].configured;sensors[sensorKey(static_cast<SensorId>(i))]["diagnostic"]=sensorDiagnostic(static_cast<SensorId>(i));}
  JsonObject diag=doc["diagnostics"].to<JsonObject>();
  diag["mpu_address"]=sensorMpuAddress();diag["mpu_who_am_i"]=sensorMpuIdentity();diag["mpu_status"]=sensorDiagnostic(SENSOR_MPU);
  diag["i2c_sda"]=I2C_SDA_PIN;diag["i2c_scl"]=I2C_SCL_PIN;diag["i2c_clock_hz"]=I2C_CLOCK_HZ;diag["nominal_supply_v"]=NOMINAL_SUPPLY_V;
  JsonObject local = doc["local_brain"].to<JsonObject>();
  local["anomaly"] = decision.anomaly;
  local["fault_type"] = decision.faultType;
  local["severity_score"] = decision.severityScore;
  local["severity_level"] = decision.severityLevel;
  local["confidence"] = 0.0f;
  local["confidence_available"] = false;
  local["confidence_kind"] = "heuristic_evidence_not_probability";
  local["trust_score"] = decision.trustScore;
  local["explanation"] = decision.explanation;
  local["warmup_complete"] = decision.warmupComplete;
  local["ewma_score"] = decision.ewmaScore;
  local["cusum_score"] = decision.cusumScore;
  local["ml_valid"] = decision.mlValid;
  JsonArray featureVector=local["feature_vector"].to<JsonArray>();
  for(float value:decision.featureVector)featureVector.add(value);
  local["ml_class"] = decision.mlClass;
  if(decision.mlValid)local["ml_probability"] = decision.mlProbability;else local["ml_probability"]=nullptr;
  local["ml_class_name"] = decision.mlClassName;
  local["ml_top_features"] = decision.mlTopFeatures;
  local["failure_risk_score"] = decision.failureRiskScore;
  local["health_index"] = decision.failureRiskScore;
  local["risk_kind"] = "heuristic_not_failure_probability";
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
  if(!decision.trusted.values.status[SENSOR_BMP].valid && !decision.trusted.estimated[SENSOR_BMP]){trusted["temperature_c"]=nullptr;trusted["pressure_hpa"]=nullptr;}
  if(!decision.trusted.values.status[SENSOR_HUMIDITY].valid && !decision.trusted.estimated[SENSOR_HUMIDITY])trusted["humidity_pct"]=nullptr;
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
  link["queue_depth"] = telemetryQueueDepth();
  link["dropped_packets"]=droppedPackets.load();link["persistent_queue"]=durableReady.load();
  link["lora_enabled"] = ENABLE_LORA;
  link["lora_available"] = loraFallbackAvailable();
  item.sequence = snapshot.sequence;
  item.critical = decision.severityScore >= 75.0f || decision.preFailureWarning;
  snprintf(item.lora,sizeof(item.lora),"%s|%s|%lu|%lu|%s|%.0f|%.0f|%s",STATION_ID,bootId,snapshot.sequence,snapshot.timestampMs,
           decision.faultType,decision.severityScore,decision.failureRiskScore,decision.stationState);
  const size_t length = serializeJson(doc, item.json, sizeof(item.json));
  return length > 0 && length < sizeof(item.json) - 1;
}

void ensureWifi() {
  static uint32_t lastAttempt=0;static bool started=false;
  if(WiFi.status()==WL_CONNECTED){const String address=WiFi.localIP().toString();portENTER_CRITICAL(&ipMux);snprintf(localIp,sizeof(localIp),"%s",address.c_str());portEXIT_CRITICAL(&ipMux);return;}
  serverReachable=false;
  if(started && uint32_t(millis()-lastAttempt)<WIFI_RETRY_MS)return;
  started=true;lastAttempt=millis();WiFi.disconnect();WiFi.mode(WIFI_STA);WiFi.setSleep(false);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
}
bool erasedPartition(){
  const esp_partition_t* partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_SPIFFS,nullptr);
  if(!partition)return false;
  static uint8_t check[1024];
  for(size_t at=0;at<partition->size;at+=sizeof(check)){
    const size_t amount=min(sizeof(check),partition->size-at);
    if(esp_partition_read(partition,at,check,amount)!=ESP_OK)return false;
    for(size_t i=0;i<amount;++i)if(check[i]!=0xff)return false;
  }
  return true;
}
void initDurable(){
  // Never auto-format an existing/corrupt filesystem. Format only a fully erased partition.
  durableReady=LittleFS.begin(false);
  if(!durableReady && erasedPartition())durableReady=LittleFS.begin(true);
  if(!durableReady){Serial.println("[QUEUE] Persistent storage unavailable; RAM queue only. Existing flash was not erased.");return;}
  File root=LittleFS.open("/");File entry=root.openNextFile();
  while(entry){
    String name=entry.name();if(!name.startsWith("/"))name="/"+name;
    if(name.startsWith("/q_")&&name.endsWith(".json")){
      unsigned long n=strtoul(name.substring(3,11).c_str(),nullptr,16);nextFile=max(nextFile,(uint32_t)n+1);
      if(durableCount<96)durablePaths[durableCount++]=name;
    }
    entry.close();entry=root.openNextFile();
  }
  for(int i=0;i<durableCount;++i)for(int j=i+1;j<durableCount;++j)if(durablePaths[j]<durablePaths[i]){String temp=durablePaths[i];durablePaths[i]=durablePaths[j];durablePaths[j]=temp;}
  durableDepth=durableCount;root.close();
}
bool removeFirst(){
  if(!durableCount)return false;
  if(!LittleFS.remove(durablePaths[0]))return false;for(int i=1;i<durableCount;++i)durablePaths[i-1]=durablePaths[i];--durableCount;durableDepth=durableCount;return true;
}
bool persist(const QueueItem& item){
  if(!durableReady)return false;
  if(durableCount>=96){if(!removeFirst())return false;++droppedPackets;}
  char path[28];snprintf(path,sizeof(path),"/q_%08lx.json",(unsigned long)nextFile++);
  File f=LittleFS.open("/pending.tmp","w");if(!f)return false;
  const size_t wanted=strlen(item.json);const bool ok=f.write((const uint8_t*)item.json,wanted)==wanted;f.flush();f.close();
  if(!ok || !LittleFS.rename("/pending.tmp",path)){LittleFS.remove("/pending.tmp");return false;}
  durablePaths[durableCount++]=path;durableDepth=durableCount;return true;
}
bool sendJson(const char* json,bool replay){
  if(WiFi.status()!=WL_CONNECTED)return false;
  JsonDocument doc;if(deserializeJson(doc,json))return false;
  const char* oldBoot=doc["boot_id"]|"";
  if(strcmp(oldBoot,bootId)==0){doc["sample_age_ms"]=(uint32_t)(millis()-(uint32_t)(doc["captured_ms"]|0U));}
  else if(doc["timestamp"].isNull()){doc["sample_age_ms"]=nullptr;doc["time_quality"]="UNVERIFIED_PREVIOUS_BOOT";}
  doc["replay"]=replay;doc.remove("captured_ms");String body;serializeJson(doc,body);
  WiFiClient client;HTTPClient http;http.setConnectTimeout(HTTP_TIMEOUT_MS);http.setTimeout(HTTP_TIMEOUT_MS);
  http.begin(client,endpoint);http.addHeader("Content-Type","application/json");http.addHeader("X-Station-Token",STATION_TOKEN);
  lastHttpCode=http.POST(body);
  const bool statusOk=lastHttpCode>=200&&lastHttpCode<300;
  JsonDocument ack;const bool parsed=statusOk && !deserializeJson(ack,http.getString());
  const bool accepted=parsed && (ack["ok"]|false) && !ack["report_id"].isNull();
  serverReachable=accepted;http.end();return accepted;
}
void worker(void *) {
  initDurable();configTime(0,0,"pool.ntp.org","time.nist.gov");
  bool pendingRam=false;
  for (;;) {
    ensureWifi();
    // Latest critical alert has its own one-item queue, independent of normal backlog.
    if(criticalQueue && xQueueReceive(criticalQueue,&criticalItem,0)==pdTRUE){
      if(sendJson(criticalItem.json,false))lastCriticalAck=criticalItem.sequence;
      else if(loraFallbackAvailable() && criticalItem.sequence!=lastLoRaSequence && loraSendPayload(criticalItem.lora))lastLoRaSequence=criticalItem.sequence;
    }
    if(pendingRam){
      if(sendJson(workerItem.json,true))pendingRam=false;
      else if(persist(workerItem))pendingRam=false;
    }
    if(!pendingRam && telemetryQueue && xQueueReceive(telemetryQueue,&workerItem,0)==pdTRUE){
      // New acquisitions are tried before archived data, maintaining a current view.
      if(workerItem.sequence!=lastCriticalAck && !sendJson(workerItem.json,false) && !persist(workerItem))pendingRam=true;
    }
    if(!pendingRam && durableCount && WiFi.status()==WL_CONNECTED){
      File f=LittleFS.open(durablePaths[0],"r");
      if(f && f.size()<sizeof(workerItem.json)){const size_t got=f.readBytes(workerItem.json,sizeof(workerItem.json)-1);workerItem.json[got]=0;f.close();
        JsonDocument check;
        if(deserializeJson(check,workerItem.json)){if(removeFirst())++droppedPackets;}
        else if(sendJson(workerItem.json,true))removeFirst();
      }else{if(f)f.close();if(removeFirst())++droppedPackets;}
    }
    vTaskDelay(pdMS_TO_TICKS(150));
  }
}
}  // namespace

void telemetryBegin() {
  if (telemetryQueue != nullptr) return;  // Never start a second buffer owner.
  endpoint = String("http://") + DASHBOARD_HOST + ":" + DASHBOARD_PORT + "/api/v1/telemetry";
  telemetryQueue = xQueueCreate(TELEMETRY_QUEUE_SIZE, sizeof(QueueItem));
  criticalQueue=xQueueCreate(1,sizeof(QueueItem));
  snprintf(bootId,sizeof(bootId),"%08lx-%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
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
    ++droppedPackets;Serial.println("[TELEMETRY] JSON payload overflow; packet not queued");
    return;
  }
  if(producerItem.critical && criticalQueue)xQueueOverwrite(criticalQueue,&producerItem);
  if(xQueueSend(telemetryQueue,&producerItem,0)!=pdTRUE){
    if(xQueueReceive(telemetryQueue,&dropItem,0)==pdTRUE)++droppedPackets;
    if(xQueueSend(telemetryQueue,&producerItem,0)!=pdTRUE)++droppedPackets;
    Serial.println("[TELEMETRY] RAM queue saturated; oldest pending sample evicted; drop counter incremented");
  }
}

bool telemetryWifiConnected() { return WiFi.status() == WL_CONNECTED; }
bool telemetryServerReachable() { return serverReachable; }
int telemetryQueueDepth() { return durableDepth+(telemetryQueue ? uxQueueMessagesWaiting(telemetryQueue) : 0); }
int telemetryLastHttpCode() { return lastHttpCode; }
const char *telemetryLocalIp() { static char copy[16];portENTER_CRITICAL(&ipMux);memcpy(copy,localIp,sizeof(copy));portEXIT_CRITICAL(&ipMux);return copy; }
const char *telemetryUrl() { return endpoint.c_str(); }
