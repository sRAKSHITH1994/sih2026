#ifndef RECOVERY_MANAGER_H
#define RECOVERY_MANAGER_H

#include "data_types.h"

void recoveryManagerBegin();
RecoveryReport recoveryManagerUpdate(const SensorSnapshot& raw);

#endif
