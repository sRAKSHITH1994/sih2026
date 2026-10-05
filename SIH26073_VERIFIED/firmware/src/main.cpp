#include <Arduino.h>

#include "alarm_manager.h"
#include "config.h"
#include "local_brain.h"
#include "sensor_manager.h"
#include "telemetry.h"
#include "station_position.h"

namespace {
unsigned long lastSampleMs=0,lastSummaryMs=0;LocalDecision currentDecision{};bool haveDecision=false;

void printCsvHeader(){
  Serial.println("CSV_HEADER,timestamp_ms,temperature_c,pressure_hpa,humidity_pct,ax,ay,az,gx,gy,gz,bus_voltage_v,current_ma,power_mw,rain_rate_mm_h,wind_speed_ms,wind_direction_deg,solar_wm2,bmp_valid,humidity_valid,mpu_valid,ina_valid,rain_valid,wind_valid,vane_valid,solar_valid,local_fault,severity,confidence,ml_class,ml_probability,failure_risk");
}

void printCsv(const SensorSnapshot& s,const LocalDecision& d){
  Serial.printf("CSV,%lu,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%d,%d,%d,%d,%d,%d,%d,%d,%s,%.2f,%.4f,%d,%.4f,%.2f\n",
    s.timestampMs,s.temperatureC,s.pressureHpa,s.humidityPct,s.ax,s.ay,s.az,s.gx,s.gy,s.gz,s.busVoltageV,s.currentMa,s.powerMw,
    s.rainRateMmH,s.windSpeedMs,s.windDirectionDeg,s.solarWm2,s.status[SENSOR_BMP].valid,s.status[SENSOR_HUMIDITY].valid,
    s.status[SENSOR_MPU].valid,s.status[SENSOR_INA].valid,s.status[SENSOR_RAIN].valid,s.status[SENSOR_WIND].valid,
    s.status[SENSOR_VANE].valid,s.status[SENSOR_SOLAR].valid,d.faultType,d.severityScore,d.confidence,d.mlClass,d.mlProbability,d.failureRiskScore);
}
}

void setup(){
  Serial.begin(SERIAL_BAUD);delay(800);Serial.println("\n=== SIH26073 VERIFIED LOCAL BRAIN 5.0 ===");
  Serial.println("20-sample window | 56 features | EWMA/CUSUM | trained edge MLP | pre-failure warning");
  alarmBegin();sensorsBegin();localBrainBegin();telemetryBegin();stationPositionBegin();printCsvHeader();
}

void loop(){
  stationPositionPollSerial();
  if(haveDecision)alarmUpdate(currentDecision);
  if(millis()-lastSampleMs<SAMPLE_INTERVAL_MS){delay(5);return;}
  lastSampleMs=millis();const SensorSnapshot snapshot=sensorsRead();currentDecision=localBrainEvaluate(snapshot);
  localBrainApplyLinkState(telemetryWifiConnected(),telemetryServerReachable(),telemetryQueueDepth(),currentDecision);stationPositionUpdate(snapshot,currentDecision);haveDecision=true;
  alarmUpdate(currentDecision);telemetryUpdate(snapshot,currentDecision);printCsv(snapshot,currentDecision);
  if(millis()-lastSummaryMs>=5000UL){
    lastSummaryMs=millis();
    Serial.printf("[LOCAL] T=%.2fC P=%.2fhPa H=%.2f%% | fault=%s severity=%s %.0f | MLP=%s %.0f%% | health-index=%.0f/100 %s | alarm=%s | WiFi=%s HTTP=%d Q=%d\n",
      snapshot.temperatureC,snapshot.pressureHpa,snapshot.humidityPct,currentDecision.faultType,currentDecision.severityLevel,
      currentDecision.severityScore,currentDecision.mlClassName,currentDecision.mlProbability*100.0f,currentDecision.failureRiskScore,
      currentDecision.stationState,alarmState(),telemetryWifiConnected()?telemetryLocalIp():"offline",telemetryLastHttpCode(),telemetryQueueDepth());
  }
}
