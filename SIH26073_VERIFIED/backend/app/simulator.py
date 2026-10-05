"""Raw stimuli only. Local predictions are computed without scenario labels."""
from datetime import datetime,timezone,timedelta
import uuid
import numpy as np
from .local_reference import LocalReference
SCENARIOS={'normal':'Normal variation','spike':'Intermittent temperature spikes','drift':'Pressure/temperature drift','frozen':'Frozen atmospheric channels',
 'erratic':'Erratic atmospheric noise','data_loss':'BMP280 disconnected','electrical':'Supply voltage sag','mechanical':'Mounting vibration',
 'station_power_failure':'Raw progressive supply sag (no forecast claim)','rain_blocked':'Blocked rain counter','wind_seized':'Seized wind sensor','vane_stuck':'Stuck vane','genuine_weather':'Shared atmospheric change across three stations'}

def channel(kind,values,configured=True,valid=True):return {'configured':configured,'attached':configured,'valid':configured and valid,'sensor_type':kind,'values':values if configured else {}}
def packet_from_row(row,station,index,boot,when,offset=0):
 sensors={
  'bmp280':channel('BMP280',{k:row.get(k) for k in ['temperature_c','pressure_hpa']},True,bool(row.get('bmp_valid',1))),
  'humidity':channel('HUMIDITY_SIM',{'humidity_pct':row.get('humidity_pct')},bool(row.get('humidity_valid',1))),
  'mpu6050':channel('MPU6050',dict(zip(['accel_x_ms2','accel_y_ms2','accel_z_ms2','gyro_x_rads','gyro_y_rads','gyro_z_rads'],[row.get(k) for k in ['ax','ay','az','gx','gy','gz']])),True,bool(row.get('mpu_valid',1))),
  'ina219':channel('INA219',{k:row.get(k) for k in ['bus_voltage_v','current_ma','power_mw']},True,bool(row.get('ina_valid',1)))}
 optional={'rain':('TIPPING_BUCKET',{'rain_rate_mm_h':row.get('rain_rate_mm_h',0),'rain_total_mm':row.get('rain_total_mm',0)}),
   'wind':('ANEMOMETER',{'wind_speed_ms':row.get('wind_speed_ms',0)}),'vane':('WIND_VANE',{'wind_direction_deg':row.get('wind_direction_deg',0)}),'solar':('PYRANOMETER',{'solar_wm2':row.get('solar_wm2',0)})}
 for key,(kind,values) in optional.items():sensors[key]=channel(kind,values,bool(row.get(key+'_valid',False)))
 return {'schema_version':'2.0','station_id':station,'station_name':'Simulation '+station,'boot_id':boot,'timestamp':when.isoformat(),'time_quality':'SIMULATED',
  'uptime_ms':index*1000,'sequence':index,'latitude':13.0033+offset*.015,'longitude':80.171+offset*.012,'source_mode':'SIMULATION','firmware_version':'HOST_REFERENCE_4',
  'sensors':sensors,'link':{'type':'VIRTUAL_TIME','queue_depth':0},'diagnostics':{'virtual_time':True,'hardware_state_machines_simulated':False}}
class StationSimulator:
 def __init__(self,seed=26073):self.seed=seed;self.reset()
 def reset(self):
  self.index=0;self.boot=uuid.uuid4().hex;self.start=datetime.now(timezone.utc).replace(microsecond=0);self.models={};self.frozen={};self.rng=np.random.default_rng(self.seed)
 def step(self,scenario,source=None,include_humidity=True):
  if scenario not in SCENARIOS:raise ValueError('Unknown scenario')
  packets=[];i=self.index
  for offset,station in [(1,'SIM_NEIGHBOR_01'),(2,'SIM_NEIGHBOR_02'),(3,'SIM_NEIGHBOR_03'),(0,'SIM_AWS_01')]:
   n=self.rng;row={'temperature_c':28+.2*np.sin(i/90)+n.normal(0,.055),'pressure_hpa':1008+.12*np.cos(i/120)+n.normal(0,.075),
    'humidity_pct':67+.8*np.sin(i/180)+n.normal(0,.16),'ax':n.normal(0,.01),'ay':n.normal(0,.01),'az':9.81+n.normal(0,.02),
    'gx':n.normal(0,.005),'gy':n.normal(0,.005),'gz':n.normal(0,.005),'bus_voltage_v':5.05+n.normal(0,.012),'current_ma':108+n.normal(0,1.5),
    'bmp_valid':1,'humidity_valid':int(include_humidity),'mpu_valid':1,'ina_valid':1}
   # Mirroring uses only finite, explicitly valid measured baselines.
   if source:
    for ch in source.get('sensors',{}).values():
     if ch.get('valid'):
      for key,value in ch.get('values',{}).items():
       if key in row and value is not None and np.isfinite(value):row[key]=float(value)+n.normal(0,.02)
   row.update(rain_rate_mm_h=4. if i%4==0 else 0.,wind_speed_ms=3.+.3*np.sin(i/3),wind_direction_deg=(120+i*4)%360,
              rain_valid=int(scenario=='rain_blocked'),wind_valid=int(scenario in ('wind_seized','vane_stuck')),vane_valid=int(scenario in ('wind_seized','vane_stuck')))
   active=i>=25
   if active and (offset==0 or scenario=='genuine_weather'):
    k=i-25
    if scenario=='spike' and k%15==0:row['temperature_c']+=12
    elif scenario=='drift':row['temperature_c']+=min(15,k*.12);row['pressure_hpa']+=min(20,k*.17)
    elif scenario=='frozen':
     saved=self.frozen.setdefault(station,{k:row[k] for k in ['temperature_c','pressure_hpa','humidity_pct']});row.update(saved)
    elif scenario=='erratic':row['temperature_c']+=n.normal(0,2);row['pressure_hpa']+=n.normal(0,3)
    elif scenario=='data_loss':row['bmp_valid']=0;row['temperature_c']=row['pressure_hpa']=None
    elif scenario=='electrical':row['bus_voltage_v']=4.1+n.normal(0,.05);row['current_ma']+=100
    elif scenario=='station_power_failure':row['bus_voltage_v']=max(2.,5.-k*.045);row['current_ma']+=k*2
    elif scenario=='rain_blocked':row['rain_rate_mm_h']=0;row['humidity_pct']=95
    elif scenario=='wind_seized':row['wind_speed_ms']=0
    elif scenario=='vane_stuck':row['wind_direction_deg']=120
    elif scenario=='mechanical':row['az']+=n.normal(0,3);row['gx']+=n.normal(0,3)
    elif scenario=='genuine_weather':
     progress=min(1,k/50);row['temperature_c']+=6*progress;row['pressure_hpa']-=7*progress;row['humidity_pct']+=12*progress
   row['power_mw']=row['bus_voltage_v']*row['current_ma']
   p=packet_from_row(row,station,i,self.boot,self.start+timedelta(seconds=i),offset)
   p['local_brain']=self.models.setdefault(station,LocalReference()).evaluate(p);packets.append(p)
  self.index+=1;return packets
simulator=StationSimulator()
