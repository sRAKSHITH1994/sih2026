#ifndef LOCAL_BRAIN_H
#define LOCAL_BRAIN_H

#include "data_types.h"

void localBrainBegin();
LocalDecision localBrainEvaluate(const SensorSnapshot& snapshot);
void localBrainApplyLinkState(bool wifiConnected, bool serverReachable, int queueDepth,
                              LocalDecision& decision);

#endif
