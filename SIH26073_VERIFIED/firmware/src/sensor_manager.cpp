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
Adafruit_BMP280 bmp;Adafruit_INA219 ina219(INA_ADDR);Adafruit_SHT31 sht31;DHT dht(DHT_DATA_PIN, HUMIDITY_SENSOR_TYPE == HUMIDITY_DHT11 ? DHT11 : DHT22);
bool bmpAttached=false,mpuAttached=false,inaAttached=false,humidityAttached=false;
char mpuDiagnostic[128]="Not initialized";int mpuWhoAmI=-1;
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
bool readRegister(uint8_t address,uint8_t reg,uint8_t* out,size_t count){
  Wire.beginTransmission(address);Wire.write(reg);
  if(Wire.endTransmission(false)!=0)return false;
  const size_t got=Wire.requestFrom(address,(uint8_t)count);
  if(got!=count){while(Wire.available())Wire.read();return false;}
  for(size_t i=0;i<count;++i)out[i]=Wire.read();
  return true;
}
bool writeRegister(uint8_t address,uint8_t reg,uint8_t value){
  Wire.beginTransmission(address);Wire.write(reg);Wire.write(value);return Wire.endTransmission()==0;
}
bool initializeMpu(){
#if ENABLE_MPU6050
  mpuAttached=false;mpuAddress=0;mpuWhoAmI=-1;
  strcpy(mpuDiagnostic,"NO_ACK: check 3.3V/GND, SDA8/SCL9, AD0, loose wires and bus pull-ups");
  for(uint8_t address:{(uint8_t)MPU_ADDR_1,(uint8_t)MPU_ADDR_2}){
    if(!i2cPresent(address))continue;
    mpuAddress=address;uint8_t id=0;
    if(!readRegister(address,0x75,&id,1)){strcpy(mpuDiagnostic,"WHO_AM_I_READ_FAILED: device acknowledged but register read failed");continue;}
    mpuWhoAmI=id;
    if(id!=0x68){snprintf(mpuDiagnostic,sizeof(mpuDiagnostic),"WRONG_CHIP: WHO_AM_I=0x%02X; MPU6050 requires 0x68",id);continue;}
    // Checked, bounded initialization: the library's reset loop has no timeout.
    if(!writeRegister(address,0x6B,0x80)){strcpy(mpuDiagnostic,"RESET_WRITE_FAILED");continue;}
    const unsigned long started=millis();bool resetCleared=false;
    while((unsigned long)(millis()-started)<500UL){uint8_t power=0;
      if(!readRegister(address,0x6B,&power,1))break;
      if(!(power&0x80)){resetCleared=true;break;}delay(5);
    }
    if(!resetCleared){strcpy(mpuDiagnostic,"RESET_TIMEOUT: reset did not verify within 500 ms");continue;}
    delay(100);
    if(!writeRegister(address,0x68,0x07)){strcpy(mpuDiagnostic,"SIGNAL_RESET_FAILED");continue;}
    delay(100);
    const bool configured=writeRegister(address,0x6B,0x01) && writeRegister(address,0x6C,0x00) &&
      writeRegister(address,0x19,9) && writeRegister(address,0x1A,(uint8_t)MPU6050_BAND_21_HZ) &&
      writeRegister(address,0x1B,(uint8_t)MPU6050_RANGE_500_DEG<<3) && writeRegister(address,0x1C,(uint8_t)MPU6050_RANGE_8_G<<3);
    delay(100);
    if(!configured){strcpy(mpuDiagnostic,"CONFIG_WRITE_FAILED: at least one register write failed");continue;}
    uint8_t ar=0,gr=0;
    if(!readRegister(address,0x1C,&ar,1)||!readRegister(address,0x1B,&gr,1)||(ar&0x18)!=0x10||(gr&0x18)!=0x08){strcpy(mpuDiagnostic,"CONFIG_VERIFY_FAILED: range registers did not match");continue;}
    mpuAttached=true;strcpy(mpuDiagnostic,"READY: chip identity and range registers verified");break;
  }
#else
  strcpy(mpuDiagnostic,"NOT_CONFIGURED");
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
  Wire.begin(I2C_SDA_PIN,I2C_SCL_PIN);Wire.setClock(I2C_CLOCK_HZ);Wire.setTimeOut(50);analogReadResolution(12);delay(50);
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
  if(bmpAttached&&i2cPresent(bmpAddress)){value.temperatureC=bmp.readTemperature();value.pressureHpa=bmp.readPressure()/100.0f;value.status[SENSOR_BMP].valid=inRange(value.temperatureC,TEMP_MIN_C,TEMP_MAX_C)&&inRange(value.pressureHpa,PRESSURE_MIN_HPA,PRESSURE_MAX_HPA);}else value.status[SENSOR_BMP].attached=false;
  if(humidityAttached){
#if HUMIDITY_SENSOR_TYPE == HUMIDITY_SHT31
    value.humidityPct=sht31.readHumidity();
#else
    value.humidityPct=dht.readHumidity();
#endif
    value.status[SENSOR_HUMIDITY].valid=inRange(value.humidityPct,HUMIDITY_MIN_PCT,HUMIDITY_MAX_PCT);
  }
  if(mpuAttached){
    uint8_t bytes[14]{};
    if(readRegister(mpuAddress,0x3B,bytes,sizeof(bytes))){
      auto word=[&](int i){return (int16_t)((uint16_t(bytes[i])<<8)|bytes[i+1]);};
      const float accelScale=9.80665f/4096.0f,gyroScale=0.01745329252f/65.5f;
      value.ax=word(0)*accelScale;value.ay=word(2)*accelScale;value.az=word(4)*accelScale;
      value.gx=word(8)*gyroScale;value.gy=word(10)*gyroScale;value.gz=word(12)*gyroScale;
      const float an=sqrtf(value.ax*value.ax+value.ay*value.ay+value.az*value.az),gn=sqrtf(value.gx*value.gx+value.gy*value.gy+value.gz*value.gz);
      // Zero acceleration is allowed (free fall); failed bus reads never become zeros.
      value.status[SENSOR_MPU].valid=isfinite(an)&&isfinite(gn)&&an<80.0f&&gn<16.0f;
      strcpy(mpuDiagnostic,value.status[SENSOR_MPU].valid?"VALID: checked 14-byte read":"OUT_OF_RANGE: inspect raw values and configured range");
    }else{strcpy(mpuDiagnostic,"READ_FAILED: incomplete I2C burst; recovery will retry");value.status[SENSOR_MPU].attached=i2cPresent(mpuAddress);}
  }
  if(inaAttached&&i2cPresent(INA_ADDR)){value.busVoltageV=ina219.getBusVoltage_V();value.currentMa=ina219.getCurrent_mA();value.powerMw=ina219.getPower_mW();value.status[SENSOR_INA].valid=inRange(value.busVoltageV,0.0f,32.0f)&&inRange(value.currentMa,-5000.0f,5000.0f)&&inRange(value.powerMw,-160000.0f,160000.0f);}else value.status[SENSOR_INA].attached=false;
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
  if(id==SENSOR_BMP||id==SENSOR_HUMIDITY||id==SENSOR_MPU||id==SENSOR_INA){Wire.end();delay(5);Wire.begin(I2C_SDA_PIN,I2C_SCL_PIN);Wire.setClock(I2C_CLOCK_HZ);Wire.setTimeOut(50);delay(5);if(id==SENSOR_BMP)return initializeBmp();if(id==SENSOR_HUMIDITY)return initializeHumidity();if(id==SENSOR_MPU)return initializeMpu();return initializeIna();}
  armOptionalPins();return true;
}

bool sensorVerify(SensorId id){
  switch(id){case SENSOR_BMP:return bmpAttached&&(i2cPresent(BMP_ADDR_1)||i2cPresent(BMP_ADDR_2));case SENSOR_HUMIDITY:return humidityAttached;case SENSOR_MPU:return mpuAttached&&(i2cPresent(MPU_ADDR_1)||i2cPresent(MPU_ADDR_2));case SENSOR_INA:return inaAttached&&i2cPresent(INA_ADDR);default:return true;}
}

const char* sensorDiagnostic(SensorId id){return id==SENSOR_MPU?mpuDiagnostic:"";}
int sensorMpuAddress(){return mpuAddress;}
int sensorMpuIdentity(){return mpuWhoAmI;}
void sensorsPrintDiagnostics(){
  Serial.printf("[I2C] SDA=%d SCL=%d clock=%luHz SDAlevel=%d SCLlevel=%d\n",I2C_SDA_PIN,I2C_SCL_PIN,(unsigned long)I2C_CLOCK_HZ,digitalRead(I2C_SDA_PIN),digitalRead(I2C_SCL_PIN));
  int count=0;for(uint8_t a=1;a<127;++a)if(i2cPresent(a)){Serial.printf("[I2C] ACK 0x%02X\n",a);++count;}
  Serial.printf("[I2C] %d devices. MPU address=0x%02X WHO_AM_I=%d: %s\n",count,mpuAddress,mpuWhoAmI,mpuDiagnostic);
}
