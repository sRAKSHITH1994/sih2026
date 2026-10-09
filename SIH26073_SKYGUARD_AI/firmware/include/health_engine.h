#ifndef HEALTH_ENGINE_H
#define HEALTH_ENGINE_H

#include "data_types.h"

void healthEngineBegin();
void healthEngineUpdate(const SensorSnapshot& raw, const FeatureVector& features,
                        const MLResult& ml, LocalDecision& decision);

#endif
