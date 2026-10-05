#ifndef ALARM_MANAGER_H
#define ALARM_MANAGER_H

#include "data_types.h"

void alarmBegin();
void alarmUpdate(const LocalDecision& decision);
const char* alarmState();

#endif
