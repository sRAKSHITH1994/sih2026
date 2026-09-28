#include "recovery_manager.h"

#include <stdio.h>
#include <string.h>

#include "sensor_manager.h"

namespace {
int invalidCycles[SENSOR_COUNT]{};int attempts[SENSOR_COUNT]{};unsigned long lastAttempt[SENSOR_COUNT]{};
}

void recoveryManagerBegin(){memset(invalidCycles,0,sizeof(invalidCycles));memset(attempts,0,sizeof(attempts));memset(lastAttempt,0,sizeof(lastAttempt));}

RecoveryReport recoveryManagerUpdate(const SensorSnapshot& raw){
  RecoveryReport report{};report.sensor=SENSOR_BMP;
  for(int i=0;i<SENSOR_COUNT;++i){
    if(!raw.status[i].configured)continue;
    if(raw.status[i].attached&&raw.status[i].valid){invalidCycles[i]=0;if(attempts[i]&&raw.status[i].valid)attempts[i]=0;continue;}
    ++invalidCycles[i];
    if(invalidCycles[i]<RECOVERY_INVALID_CYCLES||millis()-lastAttempt[i]<RECOVERY_COOLDOWN_MS||attempts[i]>=3)continue;
    lastAttempt[i]=millis();++attempts[i];report.attempted=true;report.sensor=static_cast<SensorId>(i);report.attempts=attempts[i];
    const bool electronic=i<=SENSOR_INA;strcpy(report.domain,electronic?"ELECTRONIC":"PHYSICAL");
    report.recovered=sensorRecover(report.sensor)&&sensorVerify(report.sensor);
    if(electronic)snprintf(report.action,sizeof(report.action),"I2C bus reset and sensor reinitialization; attempt %d.",attempts[i]);
    else snprintf(report.action,sizeof(report.action),"GPIO/ADC interface rearmed; physical cleaning or alignment may still be required.");
    if(report.recovered){invalidCycles[i]=0;attempts[i]=0;}
    break;
  }
  return report;
}
