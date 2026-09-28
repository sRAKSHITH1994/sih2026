#pragma once
#include "data_types.h"
#include "station_position_core.h"

void stationPositionBegin();
void stationPositionPollSerial();
void stationPositionUpdate(const SensorSnapshot& snapshot, LocalDecision& decision);
const StationPosition::Report& stationPositionReport();
bool stationPositionModelSaved();
