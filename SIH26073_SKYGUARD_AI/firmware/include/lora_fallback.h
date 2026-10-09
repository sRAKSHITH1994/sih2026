#ifndef LORA_FALLBACK_H
#define LORA_FALLBACK_H

#include "data_types.h"

void loraFallbackBegin();
bool loraFallbackAvailable();
bool loraSendCritical(const SensorSnapshot& snapshot, const LocalDecision& decision);
bool loraSendPayload(const char* payload);

#endif
