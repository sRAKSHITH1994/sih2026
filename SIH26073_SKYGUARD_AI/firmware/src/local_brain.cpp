#include "local_brain.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "edge_mlp.h"
#include "feature_engine.h"
#include "health_engine.h"
#include "recovery_manager.h"
#include "sensor_manager.h"
#include "trusted_data.h"
#include "detection_rules.h"

namespace {
EdgeRules::Engine rules;

float clampValue(float value,float low,float high){return value<low?low:(value>high?high:value);}

void setText(LocalDecision& decision,const char* fault,const char* affected,const char* explanation){
  strncpy(decision.faultType,fault,sizeof(decision.faultType)-1);
  strncpy(decision.affectedSensors,affected,sizeof(decision.affectedSensors)-1);
  strncpy(decision.explanation,explanation,sizeof(decision.explanation)-1);
}

void setSeverity(LocalDecision& decision){
  if(decision.severityScore>=80.0f)strcpy(decision.severityLevel,"CRITICAL");
  else if(decision.severityScore>=60.0f)strcpy(decision.severityLevel,"HIGH");
  else if(decision.severityScore>=35.0f)strcpy(decision.severityLevel,"WARNING");
  else if(decision.severityScore>0.0f)strcpy(decision.severityLevel,"LOW");
  else strcpy(decision.severityLevel,"NORMAL");
}

const char* sensorForClass(int classId){
  switch(classId){case 5:return "ina219";case 6:return "mpu6050";case 7:return "rain";case 8:return "wind";case 9:return "vane";default:return "bmp280,humidity";}
}

void applyRule(LocalDecision& decision,const char* fault,const char* affected,const char* explanation,float severity,float confidence){
  if(!decision.anomaly||severity>decision.severityScore){setText(decision,fault,affected,explanation);decision.confidence=confidence;}
  decision.anomaly=true;decision.severityScore=max(decision.severityScore,severity);decision.confidence=max(decision.confidence,confidence);
}
}  // namespace

void localBrainBegin(){
  rules=EdgeRules::Engine{};featureEngineBegin();trustedDataBegin();healthEngineBegin();recoveryManagerBegin();
}

LocalDecision localBrainEvaluate(const SensorSnapshot& snapshot){
  LocalDecision decision{};strcpy(decision.faultType,"NORMAL");strcpy(decision.severityLevel,"NORMAL");
  strcpy(decision.stationState,"NORMAL");strcpy(decision.explanation,"Local validation, adaptive statistics, edge MLP and hardware-health checks are normal.");
  strcpy(decision.maintenanceAction,"No immediate maintenance required; continue collecting field-health history.");
  decision.confidence=0.0f;decision.trustScore=100.0f;
  decision.trusted=trustedDataUpdate(snapshot);
  FeatureVector features = featureEngineUpdate(snapshot, decision.trusted);

const bool mpuAvailable =
    ENABLE_MPU6050 &&
    snapshot.status[SENSOR_MPU].configured &&
    snapshot.status[SENSOR_MPU].attached &&
    snapshot.status[SENSOR_MPU].valid;

if (!mpuAvailable) {
  features.x[50] = 0.0f;
}
  const MLResult ml=runEdgeML(features);
  memcpy(decision.featureVector,features.x,sizeof(features.x));
  decision.warmupComplete=features.windowReady;decision.mlValid=ml.valid;decision.mlClass=ml.classId;decision.mlProbability=ml.probability;
  strncpy(decision.mlClassName,ml.valid?ml.className:"WARMUP",sizeof(decision.mlClassName)-1);
  strncpy(decision.mlTopFeatures,ml.valid?ml.topFeatures:"Waiting for 20 samples",sizeof(decision.mlTopFeatures)-1);
  decision.ewmaScore=100.0f*clampValue(max(max(fabsf(features.x[27]),fabsf(features.x[28])),fabsf(features.x[29]))/5.0f,0.0f,1.0f);
  decision.cusumScore=100.0f*clampValue(max(max(fabsf(features.x[30]),fabsf(features.x[31])),fabsf(features.x[32]))/1.0f,0.0f,1.0f);

  
  char missing[96]="";
for(int i=0;i<SENSOR_COUNT;++i){
  if(i==SENSOR_MPU && !ENABLE_MPU6050)continue;
    if(!snapshot.status[i].configured)continue;
    if(snapshot.status[i].attached&&snapshot.status[i].valid)continue;
    if(missing[0])strncat(missing,",",sizeof(missing)-strlen(missing)-1);
    strncat(missing,sensorKey(static_cast<SensorId>(i)),sizeof(missing)-strlen(missing)-1);
  }
  if(missing[0])applyRule(decision,"DATA_LOSS",missing,"A configured sensor is missing or invalid. Recent trusted data may be retained briefly, but raw data remains marked invalid.",90.0f,0.99f);

  const auto rule=rules.evaluate(features.x,features.windowReady,NOMINAL_SUPPLY_V);
 if (rule.severity > 0) {
  const bool ruleUsesMpu =
      strcmp(rule.fault, "MECHANICAL") == 0 ||
      strcmp(rule.sensor, "mpu6050") == 0;

  if (!ruleUsesMpu || mpuAvailable) {
    applyRule(
        decision, rule.fault, rule.sensor,
        rule.reason, rule.severity, .90f
    );
  }
}

const bool modelAlert =
    ml.valid &&
    ml.classId != 0 &&
    ml.probability >= ML_MIN_CONFIDENCE &&
    (ml.classId != 6 || mpuAvailable);  if(modelAlert){
    const float severity=clampValue(40.0f+ml.probability*40.0f,0.0f,95.0f);
    if(!decision.anomaly||severity>decision.severityScore){
      char explanation[260];snprintf(explanation,sizeof(explanation),"The trained 56-feature edge MLP classified %s with %.1f%% uncalibrated model score. Strongest local contributors: %s.",ml.className,ml.probability*100.0f,ml.topFeatures);
      setText(decision,ml.className,sensorForClass(ml.classId),explanation);decision.confidence=ml.probability;
    } else if(strcmp(decision.faultType,ml.className)==0){
      decision.confidence=clampValue(decision.confidence+0.05f,0.0f,0.99f);decision.severityScore=min(100.0f,decision.severityScore+5.0f);
    }
    decision.anomaly=true;decision.severityScore=max(decision.severityScore,severity);
  }

  if(!ml.valid && !decision.anomaly) {
    strcpy(decision.faultType,"WARMING_UP");
    strcpy(decision.explanation,"Edge MLP warming up or unavailable; physical rules remain active. No calibrated confidence is available.");
  }
  healthEngineUpdate(snapshot,features,ml,decision);
  if(decision.preFailureWarning){
    const float severity=decision.failureRiskScore>=80.0f?88.0f:58.0f;
    if(!decision.anomaly||severity>decision.severityScore){char explanation[260];snprintf(explanation,sizeof(explanation),"Pre-failure warning: heuristic station-health index reached %.0f/100. %s",decision.failureRiskScore,decision.maintenanceAction);setText(decision,"STATION_DEGRADATION","ina219,station",explanation);decision.confidence=max(decision.confidence,decision.failureRiskScore/100.0f);}
    decision.anomaly=true;decision.severityScore=max(decision.severityScore,severity);
  }
  trustedDataCommit(snapshot,!decision.anomaly && features.windowReady);
  if(decision.anomaly){SensorSnapshot rejected=snapshot;for(int i=0;i<SENSOR_COUNT;++i){if(strstr(decision.affectedSensors,sensorKey(static_cast<SensorId>(i))))rejected.status[i].valid=false;}decision.trusted=trustedDataUpdate(rejected);}
  decision.recovery=recoveryManagerUpdate(snapshot);
  setSeverity(decision);
  return decision;
}

void localBrainApplyLinkState(bool wifiConnected,bool serverReachable,int queueDepth,LocalDecision& decision){
  const bool backlog=queueDepth>=TELEMETRY_QUEUE_SIZE/3;
  if(!backlog)return;
  // A communication backlog is not a probability of physical station failure.
  snprintf(decision.maintenanceAction,sizeof(decision.maintenanceAction),
           "%s link backlog is %d packet(s); check dashboard service, Wi-Fi, firewall and station power.",
           !wifiConnected?"Wi-Fi offline":(!serverReachable?"Dashboard unreachable":"Telemetry congested"),queueDepth);
  const float severity=queueDepth>=TELEMETRY_QUEUE_SIZE-2?86.0f:62.0f;
  applyRule(decision,"COMMUNICATION_FAULT","wifi,telemetry",
            "Store-and-forward backlog is growing, so the Local Brain detected a communication fault before data is lost.",severity,0.93f);
  setSeverity(decision);
}
