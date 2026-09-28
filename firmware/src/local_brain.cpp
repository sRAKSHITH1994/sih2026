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

namespace {
int frozenPersistence[3]{};

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
  memset(frozenPersistence,0,sizeof(frozenPersistence));featureEngineBegin();trustedDataBegin();healthEngineBegin();recoveryManagerBegin();
}

LocalDecision localBrainEvaluate(const SensorSnapshot& snapshot){
  LocalDecision decision{};strcpy(decision.faultType,"NORMAL");strcpy(decision.severityLevel,"NORMAL");
  strcpy(decision.stationState,"NORMAL");strcpy(decision.explanation,"Local validation, adaptive statistics, edge MLP and hardware-health checks are normal.");
  strcpy(decision.maintenanceAction,"No immediate maintenance required; continue collecting field-health history.");
  decision.confidence=0.70f;decision.trustScore=100.0f;
  decision.trusted=trustedDataUpdate(snapshot);
  const FeatureVector features=featureEngineUpdate(snapshot,decision.trusted);
  const MLResult ml=runEdgeML(features);
  decision.warmupComplete=features.windowReady;decision.mlValid=ml.valid;decision.mlClass=ml.classId;decision.mlProbability=ml.probability;
  strncpy(decision.mlClassName,ml.valid?ml.className:"WARMUP",sizeof(decision.mlClassName)-1);
  strncpy(decision.mlTopFeatures,ml.valid?ml.topFeatures:"Waiting for 20 samples",sizeof(decision.mlTopFeatures)-1);
  decision.ewmaScore=100.0f*clampValue(max(max(fabsf(features.x[27]),fabsf(features.x[28])),fabsf(features.x[29]))/5.0f,0.0f,1.0f);
  decision.cusumScore=100.0f*clampValue(max(max(fabsf(features.x[30]),fabsf(features.x[31])),fabsf(features.x[32]))/1.0f,0.0f,1.0f);

  char missing[96]="";
  for(int i=0;i<SENSOR_COUNT;++i){
    if(!snapshot.status[i].configured)continue;
    if(snapshot.status[i].attached&&snapshot.status[i].valid)continue;
    if(missing[0])strncat(missing,",",sizeof(missing)-strlen(missing)-1);
    strncat(missing,sensorKey(static_cast<SensorId>(i)),sizeof(missing)-strlen(missing)-1);
  }
  if(missing[0])applyRule(decision,"DATA_LOSS",missing,"A configured sensor is missing or invalid. Recent trusted data may be retained briefly, but raw data remains marked invalid.",90.0f,0.99f);

  if(features.windowReady&&snapshot.status[SENSOR_BMP].valid){
    const float zTemperature=fabsf(features.x[1])/max(features.x[2],0.18f);
    const float zPressure=fabsf(features.x[5])/max(features.x[6],0.35f);
    float maximumZ=max(zTemperature,zPressure);const char* strongest=zTemperature>=zPressure?"bmp280.temperature":"bmp280.pressure";
    if(snapshot.status[SENSOR_HUMIDITY].valid){const float zHumidity=fabsf(features.x[9])/max(features.x[10],0.8f);if(zHumidity>maximumZ){maximumZ=zHumidity;strongest="humidity";}}
    if(maximumZ>=5.0f)applyRule(decision,"SPIKE",strongest,"A channel changed much faster than its rolling local baseline.",clampValue(48.0f+maximumZ*6.0f,0.0f,92.0f),0.90f);

    const bool frozenT=features.x[2]<0.012f&&fabsf(features.x[3])<0.001f;
    const bool frozenP=features.x[6]<0.025f&&fabsf(features.x[7])<0.002f;
    const bool frozenH=snapshot.status[SENSOR_HUMIDITY].valid&&features.x[10]<0.04f&&fabsf(features.x[11])<0.003f;
    frozenPersistence[0]=frozenT?frozenPersistence[0]+1:0;frozenPersistence[1]=frozenP?frozenPersistence[1]+1:0;frozenPersistence[2]=frozenH?frozenPersistence[2]+1:0;
    if(frozenPersistence[0]>=5&&frozenPersistence[1]>=5&&(!snapshot.status[SENSOR_HUMIDITY].valid||frozenPersistence[2]>=5))
      applyRule(decision,"FROZEN","bmp280,humidity","Core atmospheric channels remained unnaturally unchanged across repeated full windows.",72.0f,0.94f);

    const float maximumCusum=max(max(fabsf(features.x[30]),fabsf(features.x[31])),fabsf(features.x[32]));
    const bool trend=fabsf(features.x[3])>0.20f||fabsf(features.x[7])>0.32f||(snapshot.status[SENSOR_HUMIDITY].valid&&fabsf(features.x[11])>0.45f);
    if(maximumCusum>=1.0f||trend)applyRule(decision,"DRIFT","bmp280,humidity","EWMA/CUSUM and slope evidence indicate a persistent shift from the protected local baseline.",clampValue(55.0f+maximumCusum*12.0f,0.0f,88.0f),0.86f);
  }

  if(snapshot.status[SENSOR_MPU].valid&&(features.x[13]>1.3f||fabsf(features.x[14])>1.8f||features.x[15]>2.8f))
    applyRule(decision,"MECHANICAL","mpu6050","MPU6050 detected sustained vibration, impact or station movement that may contaminate weather observations.",65.0f,0.88f);
  if(snapshot.status[SENSOR_INA].valid&&(features.x[16]<4.45f||features.x[18]>0.14f||fabsf(features.x[20])>70.0f))
    applyRule(decision,"ELECTRICAL","ina219","INA219 detected low/unstable supply or abnormal current behaviour consistent with pre-failure degradation.",74.0f,0.91f);
  if(snapshot.status[SENSOR_WIND].valid&&snapshot.status[SENSOR_VANE].valid&&features.x[33]>1.5f&&features.x[41]>.95f)
    applyRule(decision,"VANE_STUCK","vane","Wind speed remains active while wind direction is persistently unchanged.",68.0f,0.88f);
  if(snapshot.status[SENSOR_WIND].valid&&snapshot.status[SENSOR_VANE].valid&&features.x[36]>.95f&&features.x[40]>.05f)
    applyRule(decision,"WIND_SEIZED","wind","The anemometer remains at zero while the wind vane continues to move.",68.0f,0.86f);
  if(snapshot.status[SENSOR_RAIN].valid&&snapshot.status[SENSOR_HUMIDITY].valid&&features.x[8]>92.0f&&features.x[7]<-.02f&&features.x[43]<=0.0f)
    applyRule(decision,"RAIN_BLOCKED","rain","High humidity and falling pressure are inconsistent with a rain gauge reporting no tips.",62.0f,0.78f);

  const bool modelAlert=ml.valid&&ml.classId!=0&&ml.probability>=ML_MIN_CONFIDENCE;
  if(modelAlert){
    const float severity=clampValue(40.0f+ml.probability*55.0f,0.0f,95.0f);
    if(!decision.anomaly||severity>decision.severityScore){
      char explanation[260];snprintf(explanation,sizeof(explanation),"The trained 56-feature edge MLP classified %s at %.1f%% probability. Strongest local contributors: %s.",ml.className,ml.probability*100.0f,ml.topFeatures);
      setText(decision,ml.className,sensorForClass(ml.classId),explanation);decision.confidence=ml.probability;
    } else if(strcmp(decision.faultType,ml.className)==0){
      decision.confidence=clampValue(decision.confidence+0.05f,0.0f,0.99f);decision.severityScore=min(100.0f,decision.severityScore+5.0f);
    }
    decision.anomaly=true;decision.severityScore=max(decision.severityScore,severity);
  }

  healthEngineUpdate(snapshot,features,ml,decision);
  if(decision.preFailureWarning){
    const float severity=decision.failureRiskScore>=80.0f?88.0f:58.0f;
    if(!decision.anomaly||severity>decision.severityScore){char explanation[260];snprintf(explanation,sizeof(explanation),"Pre-failure warning: station-health risk reached %.0f%%. %s",decision.failureRiskScore,decision.maintenanceAction);setText(decision,"STATION_DEGRADATION","ina219,station",explanation);decision.confidence=max(decision.confidence,decision.failureRiskScore/100.0f);}
    decision.anomaly=true;decision.severityScore=max(decision.severityScore,severity);
  }
  decision.recovery=recoveryManagerUpdate(snapshot);
  setSeverity(decision);
  return decision;
}

void localBrainApplyLinkState(bool wifiConnected,bool serverReachable,int queueDepth,LocalDecision& decision){
  const bool backlog=queueDepth>=TELEMETRY_QUEUE_SIZE/3;
  if(!backlog)return;
  const float linkRisk=clampValue(35.0f+queueDepth*6.0f+(wifiConnected?0.0f:12.0f),0.0f,100.0f);
  decision.failureRiskScore=max(decision.failureRiskScore,linkRisk);
  decision.preFailureWarning=decision.failureRiskScore>=55.0f;
  if(decision.preFailureWarning)strcpy(decision.stationState,decision.failureRiskScore>=80.0f?"FAILURE_LIKELY":"DEGRADING");
  snprintf(decision.maintenanceAction,sizeof(decision.maintenanceAction),
           "%s link backlog is %d packet(s); check dashboard service, Wi-Fi, firewall and station power.",
           !wifiConnected?"Wi-Fi offline":(!serverReachable?"Dashboard unreachable":"Telemetry congested"),queueDepth);
  const float severity=queueDepth>=TELEMETRY_QUEUE_SIZE-2?86.0f:62.0f;
  applyRule(decision,"COMMUNICATION_FAULT","wifi,telemetry",
            "Store-and-forward backlog is growing, so the Local Brain detected a communication fault before data is lost.",severity,0.93f);
  setSeverity(decision);
}
