#pragma once
#include <cmath>
#include <cstring>
// Portable rule core; exercised by the same native replay used by Python tests.
namespace EdgeRules {
struct Result {int cls=0;float severity=0;const char* fault="NORMAL";const char* sensor="";const char* reason="Available rule checks normal.";};
class Engine {
 int frozen=0;
 public:
 Result evaluate(const float* f,bool ready,float nominal=5.0f) {
  Result r;
  auto take=[&](int cls,float severity,const char* fault,const char* sensor,const char* why){if(severity>r.severity){r.cls=cls;r.severity=severity;r.fault=fault;r.sensor=sensor;r.reason=why;}};
  if(f[48]>.5f && (std::fabs(f[1])>4 || std::fabs(f[5])>6 || (f[49]>.5f && std::fabs(f[9])>15)))
   take(1,82,"SPIKE","bmp280,humidity","Abrupt change exceeds configured per-second limits.");
  const bool flat=ready && f[48]>.5f && f[2]<.012f && f[6]<.025f;
  frozen=flat?frozen+1:0;
  if(frozen>=5)take(3,78,"FROZEN","bmp280","Temperature and pressure remain unchanged across repeated full windows.");
  if(ready && f[48]>.5f && !flat && ((std::fabs(f[3])>.045f && std::fabs(f[30])>1) || (std::fabs(f[7])>.075f && std::fabs(f[31])>1)))
   take(2,66,"DRIFT","bmp280","Sustained slope and CUSUM jointly exceed the local drift limits.");
  if(f[50]>.5f && (f[13]>1.3f || std::fabs(f[14])>1.8f || f[15]>2.8f))
   take(6,70,"MECHANICAL","mpu6050","Motion or vibration exceeds the configured mounting disturbance limit.");
  if(f[51]>.5f && (f[16]<nominal*.89f || (ready && f[18]>.14f) || std::fabs(f[20])>70))
   take(5,84,"ELECTRICAL","ina219","Supply voltage or current deviates from the configured monitored rail.");
  return r;
 }
};
}
