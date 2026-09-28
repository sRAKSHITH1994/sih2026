#include "health_engine.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

namespace {
float health[SENSOR_COUNT]{};

float clampValue(float value,float low,float high){return value<low?low:(value>high?high:value);}

SensorId sensorForClass(int classId) {
  switch(classId){case 5:return SENSOR_INA;case 6:return SENSOR_MPU;case 7:return SENSOR_RAIN;case 8:return SENSOR_WIND;case 9:return SENSOR_VANE;default:return SENSOR_BMP;}
}

const char* stateFor(float value,bool valid){if(!valid||value<=HEALTH_CRITICAL_THRESHOLD)return "FAULT";if(value<HEALTH_DEGRADED_THRESHOLD)return "DEGRADED";return "HEALTHY";}
}  // namespace

void healthEngineBegin(){for(int i=0;i<SENSOR_COUNT;++i)health[i]=100.0f;}

void healthEngineUpdate(const SensorSnapshot& raw,const FeatureVector& features,const MLResult& ml,LocalDecision& decision){
  int configured=0,invalid=0;
  for(int i=0;i<SENSOR_COUNT;++i){
    const bool enabled=raw.status[i].configured;
    if(!enabled){decision.health[i]=0.0f;strcpy(decision.healthState[i],"NOT_ATTACHED");continue;}
    ++configured;
    if(!raw.status[i].attached||!raw.status[i].valid){health[i]=max(0.0f,health[i]-10.0f);++invalid;}
    else health[i]=min(100.0f,health[i]+0.45f);
  }
  if(ml.valid&&ml.classId!=0&&ml.classId!=6&&ml.probability>=ML_MIN_CONFIDENCE){const SensorId blamed=sensorForClass(ml.classId);if(raw.status[blamed].configured)health[blamed]=max(0.0f,health[blamed]-(1.5f+3.5f*ml.probability));}
  float sum=0.0f;
  for(int i=0;i<SENSOR_COUNT;++i){
    if(!raw.status[i].configured)continue;
    decision.health[i]=health[i];strncpy(decision.healthState[i],stateFor(health[i],raw.status[i].valid),15);decision.healthState[i][15]='\0';sum+=health[i];
  }
  const float average=configured?sum/configured:0.0f;
  float risk=(100.0f-average)*0.65f+invalid*18.0f;
  if(raw.status[SENSOR_INA].valid){
    if(features.x[16]<4.60f)risk+=clampValue((4.60f-features.x[16])*38.0f,0.0f,45.0f);
    if(features.x[17]<-0.025f)risk+=clampValue(-features.x[17]*100.0f,0.0f,25.0f);
    if(features.x[18]>0.10f)risk+=clampValue(features.x[18]*35.0f,0.0f,20.0f);
  }
  if(ml.valid){risk+=35.0f*ml.probabilities[5]+20.0f*ml.probabilities[6];}
  if(decision.trusted.anyEstimated)risk+=8.0f;
  decision.failureRiskScore=clampValue(risk,0.0f,100.0f);
  decision.preFailureWarning=decision.failureRiskScore>=55.0f;
  if(decision.failureRiskScore>=80.0f)strcpy(decision.stationState,"FAILURE_LIKELY");
  else if(decision.failureRiskScore>=55.0f)strcpy(decision.stationState,"DEGRADING");
  else if(decision.failureRiskScore>=25.0f)strcpy(decision.stationState,"WATCH");
  else strcpy(decision.stationState,"NORMAL");
  decision.trustScore=clampValue(average-(decision.trusted.anyEstimated?8.0f:0.0f),0.0f,100.0f);
  if(invalid)snprintf(decision.maintenanceAction,sizeof(decision.maintenanceAction),"Inspect the configured sensor reported as invalid; verify power, connector and I2C/GPIO continuity.");
  else if(raw.status[SENSOR_INA].valid&&features.x[16]<4.60f)snprintf(decision.maintenanceAction,sizeof(decision.maintenanceAction),"Check station supply, battery and cable resistance; INA219 indicates a falling or low bus voltage.");
  else if(ml.valid&&ml.probabilities[6]>.45f)snprintf(decision.maintenanceAction,sizeof(decision.maintenanceAction),"Inspect enclosure mounting and vibration isolation; MPU6050 indicates increasing mechanical disturbance.");
  else snprintf(decision.maintenanceAction,sizeof(decision.maintenanceAction),"No immediate maintenance required; continue collecting field-health history.");
}
