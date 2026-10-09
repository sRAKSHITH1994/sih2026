#include <cassert>
#include <cmath>
#include <cstring>
#include "recovery_manager.h"
#include "trusted_data.h"
#include "sensor_manager.h"
static unsigned long clockMs=0;static unsigned resets=0;
unsigned long millis(){return clockMs;}
bool sensorRecover(SensorId){++resets;return true;}
int main(){
 SensorSnapshot raw{};raw.status[SENSOR_MPU]={true,false,false};recoveryManagerBegin();
 for(int i=0;i<10;++i){clockMs=i*61000UL;auto report=recoveryManagerUpdate(raw);assert(!report.recovered);}
 assert(resets>3); // no permanent stop after three attempts
 raw.status[SENSOR_MPU]={true,true,true};
 for(int i=0;i<3;++i){clockMs+=1000;auto report=recoveryManagerUpdate(raw);assert(report.recovered==(i==2));}
 trustedDataBegin();raw={};raw.status[SENSOR_BMP]={true,true,true};raw.temperatureC=25;raw.pressureHpa=1008;
 for(int i=0;i<3;++i){raw.timestampMs=1000+i*1000;trustedDataCommit(raw,true);}
 raw.timestampMs=4000;raw.temperatureC=70;trustedDataCommit(raw,false); // plausible range, rejected anomaly
 raw.timestampMs=5000;raw.status[SENSOR_BMP].valid=false;raw.temperatureC=NAN;raw.pressureHpa=NAN;
 auto recent=trustedDataUpdate(raw);assert(recent.estimated[SENSOR_BMP]);assert(recent.values.temperatureC==25);assert(recent.ageMs[SENSOR_BMP]==2000);
 assert(!recent.values.status[SENSOR_BMP].valid); // carried estimate is never marked observed-valid
 raw.timestampMs=15000;auto expired=trustedDataUpdate(raw);assert(!expired.estimated[SENSOR_BMP]);assert(!expired.values.status[SENSOR_BMP].valid);
 raw.status[SENSOR_RAIN]={true,false,false};assert(!trustedDataUpdate(raw).estimated[SENSOR_RAIN]);
}
