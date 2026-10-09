#ifndef EDGE_MLP_H
#define EDGE_MLP_H

#include "data_types.h"

MLResult runEdgeML(const FeatureVector& features);
const char* mlClassName(int classId);

#endif
