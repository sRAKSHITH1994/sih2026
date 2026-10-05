#ifndef FEATURE_ENGINE_H
#define FEATURE_ENGINE_H

#include "data_types.h"

void featureEngineBegin();
FeatureVector featureEngineUpdate(const SensorSnapshot& raw, const TrustedSnapshot& trusted);
const char* featureName(int index);

#endif
