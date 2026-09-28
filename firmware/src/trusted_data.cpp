#include "trusted_data.h"

#include <math.h>
#include <string.h>

namespace {
SensorSnapshot lastGood{};
unsigned long lastGoodAt[SENSOR_COUNT]{};
bool haveLast[SENSOR_COUNT]{};

bool fresh(SensorId id, unsigned long now) {
  return haveLast[id] && now - lastGoodAt[id] <= FALLBACK_MAX_AGE_MS;
}

void remember(const SensorSnapshot& raw, SensorId id) {
  lastGoodAt[id] = raw.timestampMs;
  haveLast[id] = true;
  switch (id) {
    case SENSOR_BMP:
      lastGood.temperatureC = raw.temperatureC; lastGood.pressureHpa = raw.pressureHpa; break;
    case SENSOR_HUMIDITY: lastGood.humidityPct = raw.humidityPct; break;
    case SENSOR_MPU:
      lastGood.ax = raw.ax; lastGood.ay = raw.ay; lastGood.az = raw.az;
      lastGood.gx = raw.gx; lastGood.gy = raw.gy; lastGood.gz = raw.gz; break;
    case SENSOR_INA:
      lastGood.busVoltageV = raw.busVoltageV; lastGood.currentMa = raw.currentMa; lastGood.powerMw = raw.powerMw; break;
    case SENSOR_WIND: lastGood.windSpeedMs = raw.windSpeedMs; break;
    case SENSOR_VANE: lastGood.windDirectionDeg = raw.windDirectionDeg; break;
    case SENSOR_SOLAR: lastGood.solarWm2 = raw.solarWm2; break;
    case SENSOR_RAIN:
      lastGood.rainRateMmH = raw.rainRateMmH; lastGood.rainTotalMm = raw.rainTotalMm; break;
    default: break;
  }
}

void restore(TrustedSnapshot& output, SensorId id) {
  output.estimated[id] = true;
  output.ageMs[id] = output.values.timestampMs - lastGoodAt[id];
  output.anyEstimated = true;
  switch (id) {
    case SENSOR_BMP:
      output.values.temperatureC = lastGood.temperatureC; output.values.pressureHpa = lastGood.pressureHpa; break;
    case SENSOR_HUMIDITY: output.values.humidityPct = lastGood.humidityPct; break;
    case SENSOR_MPU:
      output.values.ax = lastGood.ax; output.values.ay = lastGood.ay; output.values.az = lastGood.az;
      output.values.gx = lastGood.gx; output.values.gy = lastGood.gy; output.values.gz = lastGood.gz; break;
    case SENSOR_INA:
      output.values.busVoltageV = lastGood.busVoltageV; output.values.currentMa = lastGood.currentMa; output.values.powerMw = lastGood.powerMw; break;
    case SENSOR_WIND: output.values.windSpeedMs = lastGood.windSpeedMs; break;
    case SENSOR_VANE: output.values.windDirectionDeg = lastGood.windDirectionDeg; break;
    case SENSOR_SOLAR: output.values.solarWm2 = lastGood.solarWm2; break;
    default: break;
  }
}

void clearInvalidNumbers(SensorSnapshot& value) {
  if (!isfinite(value.temperatureC)) value.temperatureC = 0.0f;
  if (!isfinite(value.pressureHpa)) value.pressureHpa = 0.0f;
  if (!isfinite(value.humidityPct)) value.humidityPct = 0.0f;
  float* motion[] = {&value.ax,&value.ay,&value.az,&value.gx,&value.gy,&value.gz};
  for (float* number : motion) if (!isfinite(*number)) *number = 0.0f;
  float* other[] = {&value.busVoltageV,&value.currentMa,&value.powerMw,&value.rainRateMmH,
                    &value.rainTotalMm,&value.windSpeedMs,&value.windDirectionDeg,&value.solarWm2};
  for (float* number : other) if (!isfinite(*number)) *number = 0.0f;
}
}  // namespace

void trustedDataBegin() {
  memset(&lastGood, 0, sizeof(lastGood));
  memset(lastGoodAt, 0, sizeof(lastGoodAt));
  memset(haveLast, 0, sizeof(haveLast));
}

TrustedSnapshot trustedDataUpdate(const SensorSnapshot& raw) {
  TrustedSnapshot output{};
  output.values = raw;
  for (int index = 0; index < SENSOR_COUNT; ++index) {
    const SensorId id = static_cast<SensorId>(index);
    if (raw.status[id].attached && raw.status[id].valid) remember(raw, id);
    else if (raw.status[id].configured && fresh(id, raw.timestampMs) && id != SENSOR_RAIN) restore(output, id);
  }
  // Rain is deliberately never fabricated: a missing tipping bucket means
  // rainfall is unknown, not zero and not a carried-forward estimate.
  clearInvalidNumbers(output.values);
  return output;
}
