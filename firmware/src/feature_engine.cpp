#include "feature_engine.h"

#include <math.h>
#include <string.h>

namespace {
SensorSnapshot history[WINDOW_SIZE]{};
int historyCount = 0;
int historyHead = 0;

struct ChannelState { float ewma, baseline, positive, negative; bool initialized; };
ChannelState temperatureState{}, pressureState{}, humidityState{};
float solarReference = 0.0f;

const char* names[ML_INPUTS] = {
  "temperature","temperature_delta","temperature_std","temperature_slope",
  "pressure","pressure_delta","pressure_std","pressure_slope",
  "humidity","humidity_delta","humidity_std","humidity_slope",
  "acceleration_norm","acceleration_std","acceleration_jerk","gyro_norm",
  "bus_voltage","bus_voltage_delta","bus_voltage_std","current_ma","current_delta","current_std","power_mw","power_slope",
  "ewma_temperature","ewma_pressure","ewma_humidity","temperature_residual","pressure_residual","humidity_residual",
  "cusum_temperature","cusum_pressure","cusum_humidity",
  "wind_speed","wind_speed_std","wind_speed_slope","wind_zero_fraction","wind_gust_factor",
  "wind_direction_sin","wind_direction_cos","wind_direction_variance","wind_direction_stuck",
  "rain_rate","rain_window_accumulation","rain_humidity_inconsistency",
  "solar_irradiance","solar_std","solar_clear_ratio",
  "bmp_valid","humidity_valid","mpu_valid","ina_valid","rain_valid","wind_valid","vane_valid","solar_valid"
};

float mean(const float* values, int count) {
  float total = 0.0f; for (int i = 0; i < count; ++i) total += values[i];
  return count ? total / count : 0.0f;
}

float standardDeviation(const float* values, int count) {
  if (!count) return 0.0f;
  const float average = mean(values, count); float total = 0.0f;
  for (int i = 0; i < count; ++i) { const float delta = values[i] - average; total += delta * delta; }
  return sqrtf(total / count);
}

float slope(const float* values, int count) {
  if (count < 2) return 0.0f;
  float sx=0, sy=0, sxy=0, sxx=0;
  for (int i=0;i<count;++i) { const float x=i; sx+=x; sy+=values[i]; sxy+=x*values[i]; sxx+=x*x; }
  const float denominator=count*sxx-sx*sx;
  return fabsf(denominator)<1e-6f ? 0.0f : (count*sxy-sx*sy)/denominator;
}

float angleDifference(float a, float b) {
  float difference=fmodf(fabsf(a-b),360.0f); return difference>180.0f?360.0f-difference:difference;
}

void updateAdaptive(ChannelState& state, float value, float scale, bool valid,
                    float& ewma, float& residual, float& signedCusum) {
  if (!valid) { ewma=residual=signedCusum=0.0f; return; }
  scale=max(scale,0.001f);
  if (!state.initialized) {
    state.ewma=state.baseline=value; state.positive=state.negative=0.0f; state.initialized=true;
    ewma=state.ewma; residual=signedCusum=0.0f; return;
  }
  const float oldBaseline=state.baseline;
  state.ewma=EWMA_ALPHA*value+(1.0f-EWMA_ALPHA)*state.ewma;
  const float normalized=(value-oldBaseline)/scale;
  state.positive=max(0.0f,state.positive+normalized-CUSUM_K);
  state.negative=min(0.0f,state.negative+normalized+CUSUM_K);
  if (fabsf(normalized)<=3.0f) state.baseline=BASELINE_ALPHA*value+(1.0f-BASELINE_ALPHA)*oldBaseline;
  ewma=state.ewma; residual=(value-state.ewma)/scale;
  signedCusum=max(-4.0f,min(4.0f,(state.positive+state.negative)/CUSUM_LIMIT));
}
}  // namespace

void featureEngineBegin() {
  memset(history,0,sizeof(history)); historyCount=0; historyHead=0;
  temperatureState={};pressureState={};humidityState={};solarReference=0.0f;
}

const char* featureName(int index) { return index>=0 && index<ML_INPUTS ? names[index] : "unknown"; }

FeatureVector featureEngineUpdate(const SensorSnapshot& raw, const TrustedSnapshot& trusted) {
  history[historyHead]=trusted.values; historyHead=(historyHead+1)%WINDOW_SIZE;
  if (historyCount<WINDOW_SIZE) ++historyCount;
  float t[WINDOW_SIZE]{},p[WINDOW_SIZE]{},h[WINDOW_SIZE]{},acc[WINDOW_SIZE]{},gyro[WINDOW_SIZE]{};
  float voltage[WINDOW_SIZE]{},current[WINDOW_SIZE]{},power[WINDOW_SIZE]{},wind[WINDOW_SIZE]{};
  float vane[WINDOW_SIZE]{},rain[WINDOW_SIZE]{},solar[WINDOW_SIZE]{};
  for (int i=0;i<historyCount;++i) {
    const int index=(historyHead-historyCount+i+WINDOW_SIZE)%WINDOW_SIZE; const SensorSnapshot& s=history[index];
    t[i]=s.temperatureC;p[i]=s.pressureHpa;h[i]=s.humidityPct;
    acc[i]=sqrtf(s.ax*s.ax+s.ay*s.ay+s.az*s.az);gyro[i]=sqrtf(s.gx*s.gx+s.gy*s.gy+s.gz*s.gz);
    voltage[i]=s.busVoltageV;current[i]=s.currentMa;power[i]=s.powerMw;wind[i]=s.windSpeedMs;
    vane[i]=s.windDirectionDeg;rain[i]=s.rainRateMmH;solar[i]=s.solarWm2;
  }
  const int last=historyCount-1; const int previous=historyCount>1?last-1:last;
  FeatureVector output{}; float* f=output.x;
  f[0]=t[last];f[1]=t[last]-t[previous];f[2]=standardDeviation(t,historyCount);f[3]=slope(t,historyCount);
  f[4]=p[last];f[5]=p[last]-p[previous];f[6]=standardDeviation(p,historyCount);f[7]=slope(p,historyCount);
  f[8]=h[last];f[9]=h[last]-h[previous];f[10]=standardDeviation(h,historyCount);f[11]=slope(h,historyCount);
  f[12]=acc[last];f[13]=standardDeviation(acc,historyCount);
  f[14]=historyCount>=3?(acc[last]-acc[last-1])-(acc[last-1]-acc[last-2]):0.0f;f[15]=gyro[last];
  f[16]=voltage[last];f[17]=voltage[last]-voltage[previous];f[18]=standardDeviation(voltage,historyCount);
  f[19]=current[last];f[20]=current[last]-current[previous];f[21]=standardDeviation(current,historyCount);
  f[22]=power[last];f[23]=slope(power,historyCount);
  updateAdaptive(temperatureState,t[last],max(f[2],0.18f),raw.status[SENSOR_BMP].valid,f[24],f[27],f[30]);
  updateAdaptive(pressureState,p[last],max(f[6],0.35f),raw.status[SENSOR_BMP].valid,f[25],f[28],f[31]);
  updateAdaptive(humidityState,h[last],max(f[10],0.8f),raw.status[SENSOR_HUMIDITY].valid,f[26],f[29],f[32]);
  f[33]=wind[last];f[34]=standardDeviation(wind,historyCount);f[35]=slope(wind,historyCount);
  if (raw.status[SENSOR_WIND].valid) {
    int zero=0;float maximum=wind[0];for(int i=0;i<historyCount;++i){if(wind[i]<0.15f)++zero;maximum=max(maximum,wind[i]);}
    f[36]=(float)zero/historyCount;f[37]=maximum/(mean(wind,historyCount)+0.01f);
  }
  if (raw.status[SENSOR_VANE].valid) {
    float sumSin=0,sumCos=0;int unchanged=0;
    for(int i=0;i<historyCount;++i){const float radians=vane[i]*PI/180.0f;sumSin+=sinf(radians);sumCos+=cosf(radians);if(i&&angleDifference(vane[i],vane[i-1])<1.0f)++unchanged;}
    const float radians=vane[last]*PI/180.0f;f[38]=sinf(radians);f[39]=cosf(radians);
    const float ms=sumSin/historyCount,mc=sumCos/historyCount;f[40]=1.0f-sqrtf(ms*ms+mc*mc);f[41]=(float)unchanged/max(1,historyCount-1);
  }
  f[42]=rain[last];for(int i=0;i<historyCount;++i)f[43]+=rain[i]/3600.0f;
  if(raw.status[SENSOR_RAIN].valid&&rain[last]>0&&raw.status[SENSOR_HUMIDITY].valid)f[44]=max(0.0f,80.0f-h[last])/80.0f;
  f[45]=solar[last];f[46]=standardDeviation(solar,historyCount);
  if(raw.status[SENSOR_SOLAR].valid){solarReference=max(solar[last],solarReference*0.9995f);f[47]=solar[last]/(solarReference+1.0f);}
  for(int id=0;id<SENSOR_COUNT;++id)f[48+id]=(raw.status[id].attached&&raw.status[id].valid)?1.0f:0.0f;
  output.windowReady=historyCount>=WINDOW_SIZE;
  return output;
}
