#include <iostream>
#include <iomanip>
#include "feature_engine.h"
#include "edge_mlp.h"
#include "detection_rules.h"
int main(){
 featureEngineBegin();EdgeRules::Engine rules;SensorSnapshot s{};TrustedSnapshot unused{};
 while(std::cin>>s.timestampMs){
  std::cin>>s.temperatureC>>s.pressureHpa>>s.humidityPct>>s.ax>>s.ay>>s.az>>s.gx>>s.gy>>s.gz>>s.busVoltageV>>s.currentMa>>s.powerMw>>s.rainRateMmH>>s.windSpeedMs>>s.windDirectionDeg>>s.solarWm2;
  for(int i=0;i<SENSOR_COUNT;++i){int valid;std::cin>>valid;s.status[i]={bool(valid),bool(valid),bool(valid)};}
  auto f=featureEngineUpdate(s,unused);auto ml=runEdgeML(f);auto r=rules.evaluate(f.x,f.windowReady);
  std::cout<<std::setprecision(10)<<f.windowReady<<' '<<ml.classId<<' '<<ml.probability<<' '<<r.cls;
  for(float x:f.x)std::cout<<' '<<x;
  for(float prob:ml.probabilities)std::cout<<' '<<prob;
  std::cout<<'\n';
 }
}
