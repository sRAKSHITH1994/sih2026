#ifndef DATA_TYPES_H
#define DATA_TYPES_H

#include <Arduino.h>

#include "config.h"

enum SensorId {
  SENSOR_BMP = 0,
  SENSOR_HUMIDITY,
  SENSOR_MPU,
  SENSOR_INA,
  SENSOR_RAIN,
  SENSOR_WIND,
  SENSOR_VANE,
  SENSOR_SOLAR,
  SENSOR_COUNT
};

struct Presence { bool configured; bool attached; bool valid; };

struct SensorSnapshot {
  unsigned long timestampMs;
  unsigned long sequence;
  float temperatureC, pressureHpa, humidityPct;
  float ax, ay, az, gx, gy, gz;
  float busVoltageV, currentMa, powerMw;
  float rainRateMmH, rainTotalMm, windSpeedMs, windDirectionDeg, solarWm2;
  Presence status[SENSOR_COUNT];
};

struct TrustedSnapshot {
  SensorSnapshot values;
  bool estimated[SENSOR_COUNT];
  unsigned long ageMs[SENSOR_COUNT];
  bool anyEstimated;
};

struct FeatureVector { float x[ML_INPUTS]; bool windowReady; };

struct MLResult {
  bool valid;
  int classId;
  float probability;
  float probabilities[ML_CLASSES];
  char className[28];
  char topFeatures[120];
};

struct RecoveryReport {
  bool attempted;
  bool recovered;
  SensorId sensor;
  int attempts;
  char domain[16];
  char action[96];
};

struct LocalDecision {
  bool anomaly;
  char faultType[32];
  float severityScore;
  char severityLevel[16];
  float confidence;
  float trustScore;
  char explanation[260];
  char affectedSensors[96];
  bool warmupComplete;
  float ewmaScore;
  float cusumScore;
  float health[SENSOR_COUNT];
  char healthState[SENSOR_COUNT][16];
  bool mlValid;
  int mlClass;
  float mlProbability;
  char mlClassName[28];
  char mlTopFeatures[120];
  float failureRiskScore;
  char stationState[24];
  char maintenanceAction[180];
  bool preFailureWarning;
  TrustedSnapshot trusted;
  RecoveryReport recovery;
};

#endif
