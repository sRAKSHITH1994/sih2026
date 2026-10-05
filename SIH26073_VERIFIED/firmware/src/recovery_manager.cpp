#include "recovery_manager.h"
#include "sensor_manager.h"
#include <cstdio>
#include <cstring>
namespace { unsigned invalid[SENSOR_COUNT]{},good[SENSOR_COUNT]{},tries[SENSOR_COUNT]{};unsigned long nextAttempt[SENSOR_COUNT]{};bool pending[SENSOR_COUNT]{}; }
void recoveryManagerBegin(){for(int i=0;i<SENSOR_COUNT;++i){invalid[i]=good[i]=tries[i]=0;nextAttempt[i]=0;pending[i]=false;}}
RecoveryReport recoveryManagerUpdate(const SensorSnapshot& raw){
 RecoveryReport report{};report.sensor=SENSOR_BMP;
 for(int i=0;i<SENSOR_COUNT;++i){
  if(!raw.status[i].configured)continue;
  if(raw.status[i].attached&&raw.status[i].valid){
   invalid[i]=0;if(good[i]<3)++good[i];
   if(pending[i]&&good[i]>=3){report.recovered=true;report.sensor=static_cast<SensorId>(i);report.attempts=tries[i];std::snprintf(report.action,sizeof(report.action),"Recovery confirmed by three consecutive valid readings.");pending[i]=false;tries[i]=0;}
   continue;
  }
  good[i]=0;++invalid[i];
  if(invalid[i]<3||(tries[i]>0 && static_cast<int32_t>(millis()-nextAttempt[i])<0))continue;
  if(tries[i]<1000)++tries[i];unsigned shift=tries[i]>4?4:tries[i]-1;
  unsigned long wait=RECOVERY_COOLDOWN_MS*(1UL<<shift);if(wait>60000)wait=60000;
  nextAttempt[i]=millis()+wait;report.attempted=true;report.sensor=static_cast<SensorId>(i);report.attempts=tries[i];pending[i]=true;
  sensorRecover(report.sensor);std::snprintf(report.domain,sizeof(report.domain),"%s",i<=SENSOR_INA?"ELECTRONIC":"PHYSICAL");
  std::snprintf(report.action,sizeof(report.action),"Reinitialized; awaiting three valid samples. Retry backoff %lu ms.",wait);break;
 }
 return report;
}
