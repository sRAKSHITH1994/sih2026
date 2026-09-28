#include "sensor_manager.h"

#include <Adafruit_BMP280.h>
#include <Adafruit_INA219.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_SHT31.h>
#include <DHT.h>
#include <Wire.h>
#include <math.h>
#include <string.h>

namespace {
Adafruit_BMP280 bmp;Adafruit_MPU6050 mpu;Adafruit_INA219 ina219(INA_ADDR);Adafruit_SHT31 sht31;DHT dht(DHT_DATA_PIN, HUMIDITY_SENSOR_TYPE == HUMIDITY_DHT11 ? DHT11 : DHT22);
bool bmpAttached=false,mpuAttached=false,inaAttached=false,humidityAttached=false;
uint8_t bmpAddress=0,mpuAddress=0;unsigned long sequenceNumber=0,lastReadMs=0;
volatile uint32_t rainTips=0,windPulses=0;volatile unsigned long lastRainPulseUs=0,lastWindPulseUs=0;
uint32_t lastRainCount=0,lastWindCount=0;uint16_t rainBins[RAIN_RATE_WINDOW_SECONDS]{};int rainBin=0;uint32_t rainWindowTips=0;unsigned long rainWindowMs=0;

void IRAM_ATTR onRainTip(){const unsigned long now=micros();if(now-lastRainPulseUs>=PULSE_DEBOUNCE_US){++rainTips;lastRainPulseUs=now;}}
void IRAM_ATTR onWindPulse(){const unsigned long now=micros();if(now-lastWindPulseUs>=PULSE_DEBOUNCE_US){++windPulses;lastWindPulseUs=now;}}
bool i2cPresent(uint8_t address){Wire.beginTransmission(address);return Wire.endTransmission()==0;}
bool inRange(float value,float low,float high){return isfinite(value)&&value>=low&&value<=high;}
void setPresence(Presence& value,bool configured,bool attached){value.configured=configured;value.attached=configured&&attached;value.valid=false;}

bool initializeBmp(){
#if ENABLE_BMP280
  bmpAttached=false;
  if(i2cPresent(BMP_ADDR_1)&&bmp.begin(BMP_ADDR_1)){bmpAttached=true;bmpAddress=BMP_ADDR_1;}
  else if(i2cPresent(BMP_ADDR_2)&&bmp.begin(BMP_ADDR_2)){bmpAttached=true;bmpAddress=BMP_ADDR_2;}
  if(bmpAttached)bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,Adafruit_BMP280::SAMPLING_X2,Adafruit_BMP280::SAMPLING_X16,Adafruit_BMP280::FILTER_X16,Adafruit_BMP280::STANDBY_MS_500);
#endif
  return bmpAttached;
}
bool initializeMpu(){
#if ENABLE_MPU6050
  mpuAttached=false;
  if(i2cPresent(MPU_ADDR_1)&&mpu.begin(MPU_ADDR_1,&Wire)){mpuAttached=true;mpuAddress=MPU_ADDR_1;}
  else if(i2cPresent(MPU_ADDR_2)&&mpu.begin(MPU_ADDR_2,&Wire)){mpuAttached=true;mpuAddress=MPU_ADDR_2;}
  if(mpuAttached){mpu.setAccelerometerRange(MPU6050_RANGE_8_G);mpu.setGyroRange(MPU6050_RANGE_500_DEG);mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);}
#endif
  return mpuAttached;
}
bool initializeIna(){
#if ENABLE_INA219
  inaAttached=i2cPresent(INA_ADDR)&&ina219.begin(&Wire);if(inaAttached)ina219.setCalibration_32V_2A();
#endif
  return inaAttached;
}
bool initializeHumidity() {
#if ENABLE_EXTERNAL_HUMIDITY && HUMIDITY_SENSOR_TYPE == HUMIDITY_SHT31
  humidityAttached = i2cPresent(SHT31_ADDR) && sht31.begin(SHT31_ADDR);

#elif ENABLE_EXTERNAL_HUMIDITY && \
    (HUMIDITY_SENSOR_TYPE == HUMIDITY_DHT22 || \
     HUMIDITY_SENSOR_TYPE == HUMIDITY_DHT11)
  dht.begin();
  humidityAttached = true;

#else
  humidityAttached = false;
#endif

  return humidityAttached;
}

void armOptionalPins(){
#if ENABLE_RAIN_GAUGE
  pinMode(RAIN_PIN,INPUT_PULLUP);detachInterrupt(digitalPinToInterrupt(RAIN_PIN));attachInterrupt(digitalPinToInterrupt(RAIN_PIN),onRainTip,FALLING);
#endif
#if ENABLE_ANEMOMETER
  pinMode(ANEMOMETER_PIN,INPUT_PULLUP);detachInterrupt(digitalPinToInterrupt(ANEMOMETER_PIN));attachInterrupt(digitalPinToInterrupt(ANEMOMETER_PIN),onWindPulse,FALLING);
#endif
#if ENABLE_WIND_VANE
  pinMode(WIND_VANE_PIN,INPUT);analogSetPinAttenuation(WIND_VANE_PIN,ADC_11db);
#endif
#if ENABLE_PYRANOMETER
  pinMode(PYRANOMETER_PIN,INPUT);analogSetPinAttenuation(PYRANOMETER_PIN,ADC_11db);
#endif
}

float vaneDegrees(int raw){
#if WIND_VANE_USE_LUT
  const int adc[16]={264,336,368,508,736,976,1148,1624,1844,2400,2524,2808,3144,3308,3556,3784};
  const float degrees[16]={112.5f,67.5f,90.0f,157.5f,135.0f,202.5f,180.0f,22.5f,45.0f,247.5f,225.0f,337.5f,0.0f,292.5f,315.0f,270.0f};
  int best=0;for(int i=1;i<16;++i)if(abs(raw-adc[i])<abs(raw-adc[best]))best=i;return degrees[best];
#else
  return (raw-WIND_VANE_ADC_MIN_CAL)*360.0f/max(1,WIND_VANE_ADC_MAX_CAL-WIND_VANE_ADC_MIN_CAL);
#endif
}

void advanceRainWindow(unsigned long now){
  if(!rainWindowMs){rainWindowMs=now;return;}
  unsigned long seconds=(now-rainWindowMs)/1000UL;seconds=min(seconds,(unsigned long)RAIN_RATE_WINDOW_SECONDS);
  for(unsigned long i=0;i<seconds;++i){rainBin=(rainBin+1)%RAIN_RATE_WINDOW_SECONDS;rainWindowTips-=rainBins[rainBin];rainBins[rainBin]=0;}
  rainWindowMs+=seconds*1000UL;
}
}  // namespace

const char* sensorKey(SensorId id){static const char* keys[SENSOR_COUNT]={"bmp280","humidity","mpu6050","ina219","rain","wind","vane","solar"};return keys[id];}

const char* humiditySensorName() {
#if ENABLE_EXTERNAL_HUMIDITY && HUMIDITY_SENSOR_TYPE == HUMIDITY_SHT31
  return "SHT31";
#elif ENABLE_EXTERNAL_HUMIDITY && HUMIDITY_SENSOR_TYPE == HUMIDITY_DHT22
  return "DHT22";
#elif ENABLE_EXTERNAL_HUMIDITY && HUMIDITY_SENSOR_TYPE == HUMIDITY_DHT11
  return "DHT11";
#else
  return "NOT_CONFIGURED";
#endif
}

void sensorsBegin(){
  Wire.begin(I2C_SDA_PIN,I2C_SCL_PIN);Wire.setClock(100000);analogReadResolution(12);delay(50);
  initializeBmp();initializeMpu();initializeIna();initializeHumidity();armOptionalPins();lastReadMs=millis();rainWindowMs=lastReadMs;
  Serial.printf("[SENSORS] BMP280 %s 0x%02X | MPU6050 %s 0x%02X | INA219 %s | Humidity(%s) %s\n",bmpAttached?"OK":"FAIL",bmpAddress,mpuAttached?"OK":"FAIL",mpuAddress,inaAttached?"OK":"FAIL",humiditySensorName(),humidityAttached?"OK":"NOT ATTACHED");
  Serial.printf("[OPTIONAL] rain=%s wind=%s vane=%s solar=%s\n",ENABLE_RAIN_GAUGE?"ENABLED":"NOT ATTACHED",ENABLE_ANEMOMETER?"ENABLED":"NOT ATTACHED",ENABLE_WIND_VANE?"ENABLED":"NOT ATTACHED",ENABLE_PYRANOMETER?"ENABLED":"NOT ATTACHED");
}

SensorSnapshot sensorsRead(){
  SensorSnapshot value{};value.timestampMs=millis();value.sequence=sequenceNumber++;
  value.temperatureC=value.pressureHpa=value.humidityPct=NAN;value.ax=value.ay=value.az=value.gx=value.gy=value.gz=NAN;
  value.busVoltageV=value.currentMa=value.powerMw=NAN;value.rainRateMmH=value.rainTotalMm=value.windSpeedMs=value.windDirectionDeg=value.solarWm2=NAN;
  setPresence(value.status[SENSOR_BMP],ENABLE_BMP280,bmpAttached);setPresence(value.status[SENSOR_HUMIDITY],ENABLE_EXTERNAL_HUMIDITY,humidityAttached);
  setPresence(value.status[SENSOR_MPU],ENABLE_MPU6050,mpuAttached);setPresence(value.status[SENSOR_INA],ENABLE_INA219,inaAttached);
  setPresence(value.status[SENSOR_RAIN],ENABLE_RAIN_GAUGE,ENABLE_RAIN_GAUGE);setPresence(value.status[SENSOR_WIND],ENABLE_ANEMOMETER,ENABLE_ANEMOMETER);
  setPresence(value.status[SENSOR_VANE],ENABLE_WIND_VANE,ENABLE_WIND_VANE);setPresence(value.status[SENSOR_SOLAR],ENABLE_PYRANOMETER,ENABLE_PYRANOMETER);
  if(bmpAttached){value.temperatureC=bmp.readTemperature();value.pressureHpa=bmp.readPressure()/100.0f;value.status[SENSOR_BMP].valid=inRange(value.temperatureC,TEMP_MIN_C,TEMP_MAX_C)&&inRange(value.pressureHpa,PRESSURE_MIN_HPA,PRESSURE_MAX_HPA);}
  if(humidityAttached){
#if HUMIDITY_SENSOR_TYPE == HUMIDITY_SHT31
    value.humidityPct=sht31.readHumidity();
#else
    value.humidityPct=dht.readHumidity();
#endif
    value.status[SENSOR_HUMIDITY].valid=inRange(value.humidityPct,HUMIDITY_MIN_PCT,HUMIDITY_MAX_PCT);
  }
  if(mpuAttached){sensors_event_t acceleration,gyro,temperature;mpu.getEvent(&acceleration,&gyro,&temperature);value.ax=acceleration.acceleration.x;value.ay=acceleration.acceleration.y;value.az=acceleration.acceleration.z;value.gx=gyro.gyro.x;value.gy=gyro.gyro.y;value.gz=gyro.gyro.z;const float accelerationNorm=sqrtf(value.ax*value.ax+value.ay*value.ay+value.az*value.az),gyroNorm=sqrtf(value.gx*value.gx+value.gy*value.gy+value.gz*value.gz);value.status[SENSOR_MPU].valid=isfinite(accelerationNorm)&&isfinite(gyroNorm)&&accelerationNorm<80.0f&&gyroNorm<12.0f;}
  if(inaAttached){value.busVoltageV=ina219.getBusVoltage_V();value.currentMa=ina219.getCurrent_mA();value.powerMw=ina219.getPower_mW();value.status[SENSOR_INA].valid=inRange(value.busVoltageV,0.0f,32.0f)&&inRange(value.currentMa,-5000.0f,5000.0f)&&inRange(value.powerMw,-160000.0f,160000.0f);}
  noInterrupts();const uint32_t rainCount=rainTips,windCount=windPulses;interrupts();
#if ENABLE_ANEMOMETER
  const unsigned long elapsedMs=lastReadMs?value.timestampMs-lastReadMs:SAMPLE_INTERVAL_MS;
  const float elapsedSeconds=max(0.001f,elapsedMs/1000.0f);
#endif
#if ENABLE_RAIN_GAUGE
  advanceRainWindow(value.timestampMs);const uint32_t newTips=rainCount-lastRainCount;rainBins[rainBin]+=newTips;rainWindowTips+=newTips;value.rainTotalMm=rainCount*RAIN_MM_PER_TIP;value.rainRateMmH=rainWindowTips*RAIN_MM_PER_TIP*(3600.0f/RAIN_RATE_WINDOW_SECONDS);value.status[SENSOR_RAIN].valid=inRange(value.rainRateMmH,0.0f,300.0f);
#endif
#if ENABLE_ANEMOMETER
  value.windSpeedMs=((windCount-lastWindCount)/elapsedSeconds)*WIND_MS_PER_HZ;value.status[SENSOR_WIND].valid=inRange(value.windSpeedMs,0.0f,75.0f);
#endif
#if ENABLE_WIND_VANE
  {const int raw=analogRead(WIND_VANE_PIN);value.status[SENSOR_VANE].attached=raw>ADC_OPEN_LOW&&raw<ADC_OPEN_HIGH;if(value.status[SENSOR_VANE].attached){value.windDirectionDeg=vaneDegrees(raw);value.status[SENSOR_VANE].valid=inRange(value.windDirectionDeg,0.0f,360.0f);}}
#endif
#if ENABLE_PYRANOMETER
  {const int raw=analogRead(PYRANOMETER_PIN);value.solarWm2=raw*SOLAR_WM2_PER_COUNT;value.status[SENSOR_SOLAR].valid=inRange(value.solarWm2,0.0f,1600.0f);}
#endif
  lastRainCount=rainCount;lastWindCount=windCount;lastReadMs=value.timestampMs;return value;
}

bool sensorRecover(SensorId id){
  if(id==SENSOR_BMP||id==SENSOR_HUMIDITY||id==SENSOR_MPU||id==SENSOR_INA){Wire.end();delay(5);Wire.begin(I2C_SDA_PIN,I2C_SCL_PIN);Wire.setClock(400000);delay(5);if(id==SENSOR_BMP)return initializeBmp();if(id==SENSOR_HUMIDITY)return initializeHumidity();if(id==SENSOR_MPU)return initializeMpu();return initializeIna();}
  armOptionalPins();return true;
}

bool sensorVerify(SensorId id){
  switch(id){case SENSOR_BMP:return bmpAttached&&(i2cPresent(BMP_ADDR_1)||i2cPresent(BMP_ADDR_2));case SENSOR_HUMIDITY:return humidityAttached;case SENSOR_MPU:return mpuAttached&&(i2cPresent(MPU_ADDR_1)||i2cPresent(MPU_ADDR_2));case SENSOR_INA:return inaAttached&&i2cPresent(INA_ADDR);default:return true;}
}
