#ifndef TELEMETRY_H
#define TELEMETRY_H

#include "data_types.h"

void telemetryBegin();
void telemetryUpdate(const SensorSnapshot& snapshot,const LocalDecision& decision);
bool telemetryWifiConnected();
bool telemetryServerReachable();
int telemetryQueueDepth();
int telemetryLastHttpCode();
const char* telemetryLocalIp();
const char* telemetryUrl();

#endif
