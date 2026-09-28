#ifndef TRUSTED_DATA_H
#define TRUSTED_DATA_H

#include "data_types.h"

void trustedDataBegin();
TrustedSnapshot trustedDataUpdate(const SensorSnapshot& raw);

#endif
