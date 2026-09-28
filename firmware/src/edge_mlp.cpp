#include "edge_mlp.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "feature_engine.h"
#include "model_weights.h"

namespace {
const char* classes[ML_CLASSES] = {"NORMAL","SPIKE","DRIFT","FROZEN","ERRATIC","ELECTRICAL","MECHANICAL","RAIN_BLOCKED","WIND_SEIZED","VANE_STUCK"};
float relu(float value) { return value > 0.0f ? value : 0.0f; }

void softmax(const float* logits, float* probabilities) {
  float maximum=logits[0],sum=0.0f;
  for(int i=1;i<ML_CLASSES;++i)maximum=max(maximum,logits[i]);
  for(int i=0;i<ML_CLASSES;++i){probabilities[i]=expf(logits[i]-maximum);sum+=probabilities[i];}
  for(int i=0;i<ML_CLASSES;++i)probabilities[i]/=max(sum,1e-9f);
}
}  // namespace

const char* mlClassName(int classId) { return classId>=0&&classId<ML_CLASSES?classes[classId]:"UNKNOWN"; }

MLResult runEdgeML(const FeatureVector& features) {
  MLResult output{};
  if (!features.windowReady || features.x[48] < 0.5f) return output;
  float normalized[ML_INPUTS],hidden1[ML_HIDDEN_1]{},hidden2[ML_HIDDEN_2]{},logits[ML_CLASSES]{};
  for(int i=0;i<ML_INPUTS;++i)normalized[i]=(features.x[i]-INPUT_MEAN[i])/INPUT_STD[i];
  for(int j=0;j<ML_HIDDEN_1;++j){float sum=ML_B1[j];for(int i=0;i<ML_INPUTS;++i)sum+=normalized[i]*ML_W1[i][j];hidden1[j]=relu(sum);}
  for(int j=0;j<ML_HIDDEN_2;++j){float sum=ML_B2[j];for(int i=0;i<ML_HIDDEN_1;++i)sum+=hidden1[i]*ML_W2[i][j];hidden2[j]=relu(sum);}
  for(int j=0;j<ML_CLASSES;++j){float sum=ML_B3[j];for(int i=0;i<ML_HIDDEN_2;++i)sum+=hidden2[i]*ML_W3[i][j];logits[j]=sum;}
  softmax(logits,output.probabilities);output.classId=0;
  for(int i=1;i<ML_CLASSES;++i)if(output.probabilities[i]>output.probabilities[output.classId])output.classId=i;
  output.probability=output.probabilities[output.classId];output.valid=true;
  strncpy(output.className,mlClassName(output.classId),sizeof(output.className)-1);

  // Gradient × input gives a compact edge attribution without running SHAP on
  // the microcontroller. Exact Shapley attribution is performed by the server.
  float contribution[ML_INPUTS]{};
  for(int i=0;i<ML_INPUTS;++i){
    float gradient=0.0f;
    for(int j=0;j<ML_HIDDEN_1;++j){
      if(hidden1[j]<=0.0f)continue;
      float downstream=0.0f;
      for(int k=0;k<ML_HIDDEN_2;++k)if(hidden2[k]>0.0f)downstream+=ML_W2[j][k]*ML_W3[k][output.classId];
      gradient+=ML_W1[i][j]*downstream;
    }
    contribution[i]=fabsf(normalized[i]*gradient);
  }
  int top[3]={0,0,0};float score[3]={-1,-1,-1};
  for(int i=0;i<ML_INPUTS;++i){for(int rank=0;rank<3;++rank){if(contribution[i]>score[rank]){for(int shift=2;shift>rank;--shift){score[shift]=score[shift-1];top[shift]=top[shift-1];}score[rank]=contribution[i];top[rank]=i;break;}}}
  snprintf(output.topFeatures,sizeof(output.topFeatures),"%s, %s, %s",featureName(top[0]),featureName(top[1]),featureName(top[2]));
  return output;
}
