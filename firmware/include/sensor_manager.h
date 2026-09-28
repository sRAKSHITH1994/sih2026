#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include "data_types.h"

void sensorsBegin();
SensorSnapshot sensorsRead();
const char* sensorKey(SensorId id);
const char* humiditySensorName();
bool sensorRecover(SensorId id);
bool sensorVerify(SensorId id);

#endif
