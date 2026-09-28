#include "station_position_core.h"
#include <cassert>
#include <cstdio>

using namespace StationPosition;
static void sample(Monitor& m, uint32_t t, float angle=0, bool valid=true, float gyro=0) {
  const float rad=angle/RadToDeg;
  m.update(t,true,valid,9.81f*std::sin(rad),0,9.81f*std::cos(rad),gyro,0,0);
}
static Monitor trained() {
  Monitor m; m.calibrate(0);
  for (unsigned n=0;n<30;++n) sample(m,n*1000,0.2f*std::sin(float(n)));
  assert(m.report.calibrated && m.report.modelChanged);
  assert(!m.report.active && m.model.toleranceDeg==10);
  return m;
}
int main() {
  // Upright/constant samples and small tolerable movements are normal.
  Monitor m=trained();
  for (uint32_t t=30000;t<90000;t+=1000) sample(m,t,2);
  assert(!m.report.active);
  // A 90 degree fall has the SAME acceleration norm; persistent direction matters.
  for (uint32_t t=90000;t<=93000;t+=1000) sample(m,t,90);
  assert(m.report.active && m.report.critical);
  for (uint32_t t=94000;t<110000;t+=1000) sample(m,t,90);
  assert(m.report.active && m.report.critical);
  // Reboot/model reload while fallen must not learn a new normal.
  Monitor rebooted; assert(rebooted.restore(m.model));
  for (uint32_t t=0;t<=3000;t+=1000) sample(rebooted,t,90);
  assert(rebooted.report.active && rebooted.report.critical);
  // No invalid or dynamic sample can clear the alarm.
  for (uint32_t t=4000;t<14000;t+=1000) sample(rebooted,t,0,false);
  assert(rebooted.report.active && !rebooted.report.measurementValid);
  for (uint32_t t=14000;t<24000;t+=1000) sample(rebooted,t,0,true,1);
  assert(rebooted.report.active && !rebooted.report.measurementValid);
  for (uint32_t t=24000;t<29000;t+=1000) sample(rebooted,t);
  assert(rebooted.report.active);
  sample(rebooted,29000);
  assert(!rebooted.report.active);
  // One-sample bump doesn't trigger a latched mounting alert.
  sample(rebooted,30000,70); sample(rebooted,31000,0);
  assert(!rebooted.report.active);
  // Slow displacement is detectable even with negligible gyro.
  for (uint32_t t=32000;t<=35000;t+=1000) sample(rebooted,t,18);
  assert(rebooted.report.active && !rebooted.report.critical);
  // Confirmation requires continuity; a missing interval does not count.
  Monitor gap; assert(gap.restore(m.model));
  sample(gap,1000,90); sample(gap,10000,90); sample(gap,11000,90);
  assert(!gap.report.active);
  sample(gap,12000,90); sample(gap,13000,90);
  assert(gap.report.critical);
  // Millisecond wraparound, invalid vector and missing MPU.
  Monitor wrap; assert(wrap.restore(m.model));
  for (uint32_t dt=0;dt<=3000;dt+=1000) sample(wrap,uint32_t(0xffffff00U+dt),90);
  assert(wrap.report.critical);
  Monitor bad;
  bad.calibrate(0);
  for(uint32_t t=0;t<40000;t+=1000) bad.update(t,true,true,NAN,0,9.81f,0,0,0);
  assert(!bad.report.calibrated && !bad.report.active);
  bad.update(41000,true,true,0,0,0,0,0,0);
  assert(!bad.report.sampleValid);
  // Mounting the board on its side is valid if that's the intended reference.
  Monitor side; side.calibrate(0);
  for(uint32_t t=0;t<30000;t+=1000) side.update(t,true,true,0,9.81f,0,0,0,0);
  assert(side.report.calibrated);
  for(uint32_t t=30000;t<=33000;t+=1000) side.update(t,true,true,0,0,9.81f,0,0,0);
  assert(side.report.critical);
  // Reject corrupt flash model; constant readings alone aren't a frozen fault.
  Model corrupt=m.model; corrupt.unit[0]=NAN;
  Monitor invalidModel; assert(!invalidModel.restore(corrupt));
  Monitor stationary; stationary.calibrate(0);
  for(uint32_t t=0;t<80000;t+=1000) sample(stationary,t);
  assert(stationary.report.calibrated && !stationary.report.active);
  // A new invalid sample interrupts pending confirmation.
  Monitor interrupted; assert(interrupted.restore(m.model));
  sample(interrupted,0,90); sample(interrupted,1000,90); sample(interrupted,2000,90,false);
  sample(interrupted,3000,90); sample(interrupted,4000,90);
  assert(!interrupted.report.active);
  std::puts("PASS: stationary/noise, sustained tilt/fall, persistent alarm, reboot, invalid/moving samples, recovery, transient rejection, gaps, wraparound, arbitrary mounting, corrupt model.");
}
