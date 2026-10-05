#include "station_position.h"
#include <Preferences.h>
#include <cstdio>
#include <cstring>

namespace {
StationPosition::Monitor monitor;
bool saved = false;
char command[32]{};
unsigned commandLength = 0;
bool commandOverflow = false;
uint32_t lastPrint = 0;
const char* lastState = "";

void printStatus() {
  const auto& p = monitor.report;
  Serial.printf("[POSITION] %s | tilt=%.1fdeg tolerance=%.1fdeg | calibration=%u/30 | saved=%s | alert=%s\n",
      p.state, p.tiltDeg, p.toleranceDeg, p.samples, saved?"YES":"NO", p.active?"YES":"NO");
}
}

void stationPositionBegin() {
  monitor = StationPosition::Monitor{};
  saved = false; commandLength = 0; commandOverflow = false;
  Preferences storage;
  if (storage.begin("station-pose", true)) {
    StationPosition::Model model;
    if (storage.getBytesLength("model") == sizeof(model) &&
        storage.getBytes("model", &model, sizeof(model)) == sizeof(model)) saved = monitor.restore(model);
    storage.end();
  }
  Serial.println(saved ? "[POSITION] Saved orientation loaded; no automatic recalibration." :
      "[POSITION] Uncalibrated. Secure station upright, then send MPUCAL and Enter; hold still for 30 samples.");
  Serial.println("[POSITION] Commands: MPUCAL (learn intended pose), MPUSTATUS (show state).");
}

void stationPositionPollSerial() {
  // Bounded, non-blocking command input; does not wait for characters.
  for (unsigned budget=0; budget<32 && Serial.available(); ++budget) {
    const char c = static_cast<char>(Serial.read());
    if (c=='\r' || c=='\n') {
      command[commandLength] = '\0';
      if (!commandOverflow && std::strcmp(command,"MPUCAL")==0) {
        monitor.calibrate(static_cast<uint32_t>(millis()));
        Serial.println("[POSITION] Calibration started. Keep the station fixed in its intended position for 30 samples.");
      } else if (!commandOverflow && std::strcmp(command,"MPUSTATUS")==0) printStatus();
      else if (commandLength || commandOverflow) Serial.println("[POSITION] Use MPUCAL or MPUSTATUS, then Enter.");
      commandLength=0; commandOverflow=false;
    } else if (commandLength < sizeof(command)-1) command[commandLength++]=c;
    else commandOverflow=true;
  }
}

void stationPositionUpdate(const SensorSnapshot& s, LocalDecision& d) {
  monitor.update(static_cast<uint32_t>(s.timestampMs), s.status[SENSOR_MPU].configured,
      s.status[SENSOR_MPU].attached && s.status[SENSOR_MPU].valid, s.ax,s.ay,s.az,s.gx,s.gy,s.gz);
  const auto& p = monitor.report;
  if (p.modelChanged) {
    Preferences storage;
    saved=false;
    if (storage.begin("station-pose",false)) {
      saved=storage.putBytes("model",&monitor.model,sizeof(monitor.model))==sizeof(monitor.model);
      storage.end();
    }
    Serial.println(saved ? "[POSITION] CALIBRATION SAVED. This pose remains the reference after restart." :
        "[POSITION] SAVE FAILED. Model works only this session; fix NVS storage and repeat MPUCAL.");
  }
  if (p.active) {
    const float previousSeverity = d.severityScore;
    char previousFault[sizeof(d.faultType)];
    std::snprintf(previousFault,sizeof(previousFault),"%s",d.faultType);
    const char* label = p.critical ? "STATION_FALLEN" : "STATION_TILTED";
    const float severity = p.critical ? 90.0f : 65.0f;
    d.anomaly=true;
    d.severityScore = previousSeverity > severity ? previousSeverity : severity;
    // A heuristic evidence score, NOT a calibrated ML probability of failure.
    d.confidence = p.critical ? 0.95f : 0.90f;
    std::snprintf(d.stationState,sizeof(d.stationState),"OUT_OF_POSITION");
    std::snprintf(d.severityLevel,sizeof(d.severityLevel),"%s",
        d.severityScore>=80 ? "CRITICAL" : d.severityScore>=60 ? "HIGH" : "WARNING");
    std::snprintf(d.faultType,sizeof(d.faultType),"%s",label);
    if (!std::strstr(d.affectedSensors,"station")) {
      const size_t used = std::strlen(d.affectedSensors);
      std::snprintf(d.affectedSensors+used,sizeof(d.affectedSensors)-used,"%sstation",used?",":"");
    }
    char reason[190];
    if (p.measurementValid)
      std::snprintf(reason,sizeof(reason),"Station tilt %.1f deg exceeds learned %.1f deg tolerance. MPU data is valid; this is a mounting/orientation alarm, not evidence of a broken sensor.",p.tiltDeg,p.toleranceDeg);
    else std::snprintf(reason,sizeof(reason),"Previous station-position alarm remains active; current MPU tilt is unavailable or unsettled. Return to the reference pose and verify valid readings.");
    if (std::strcmp(previousFault,"NORMAL")!=0)
      std::snprintf(d.explanation,sizeof(d.explanation),"%s Also reported: %s (severity %.0f).",reason,previousFault,previousSeverity);
    else std::snprintf(d.explanation,sizeof(d.explanation),"%s",reason);
    std::snprintf(d.maintenanceAction,sizeof(d.maintenanceAction),"Inspect and secure the station mounting. Return within %.1f deg of the saved pose for 5 s. Other faults may still require attention.",p.toleranceDeg*0.6f);
  } else if (!p.calibrated && s.status[SENSOR_MPU].configured) {
    if (std::strcmp(d.stationState,"NORMAL")==0)
      std::snprintf(d.stationState,sizeof(d.stationState),"POSE_NOT_CALIBRATED");
    if (!d.anomaly) std::snprintf(d.maintenanceAction,sizeof(d.maintenanceAction),"Station-position protection is not calibrated. Secure the station correctly, send MPUCAL, and keep still for 30 samples.");
  }
  const uint32_t now=static_cast<uint32_t>(millis());
  if (std::strcmp(lastState,p.state)!=0 || uint32_t(now-lastPrint)>=5000) {
    printStatus(); lastPrint=now; lastState=p.state;
  }
}

const StationPosition::Report& stationPositionReport() { return monitor.report; }
bool stationPositionModelSaved() { return saved; }
