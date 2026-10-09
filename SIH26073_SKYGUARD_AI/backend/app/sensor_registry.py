import math
from .schemas import EXPECTED
LABELS={'bmp280':'BMP280 temperature / pressure','humidity':'External humidity','mpu6050':'MPU6050 position / motion','ina219':'INA219 supply','rain':'Rain gauge','wind':'Anemometer','vane':'Wind vane','solar':'Pyranometer'}
SENSOR_DEFINITIONS={k:{'label':LABELS[k],'expected':list(v)} for k,v in EXPECTED.items()}
def flatten_sensor_values(packet):
 values={};active=[]
 for key,expected in EXPECTED.items():
  s=packet.get('sensors',{}).get(key,{})
  if not s.get('attached') or not s.get('valid'):continue
  clean={k:float(v) for k,v in s.get('values',{}).items() if k in expected and isinstance(v,(int,float)) and math.isfinite(float(v))}
  if len(clean)!=len(expected):continue
  active.append(key);values.update(clean)
 if 'mpu6050' in active:
  values['accel_norm_ms2']=math.sqrt(sum(values[f'accel_{a}_ms2']**2 for a in 'xyz'))
  values['gyro_norm_rads']=math.sqrt(sum(values[f'gyro_{a}_rads']**2 for a in 'xyz'))
 return values,active

def hardware_status(packet,fresh=True,decision=None):
 result=[];evidence=(decision or {}).get('evidence',{});lstm=evidence.get('lstm',{});second=evidence.get('second_opinion',{})
 for key,definition in SENSOR_DEFINITIONS.items():
  s=packet.get('sensors',{}).get(key,{})
  configured=s.get('configured',s.get('attached',False));attached=bool(s.get('attached'));valid=attached and bool(s.get('valid'))
  status='Not configured' if not configured else 'Offline / stale' if not fresh else 'Not detected' if not attached else 'Invalid readings' if not valid else 'Valid readings'
  model_used=fresh and valid and (second.get('available') or (key=='bmp280' and lstm.get('ready')) or (key=='humidity' and lstm.get('ready') and lstm.get('profile')=='TPH'))
  result.append({'key':key,'label':definition['label'],'configured':configured,'attached':attached,'valid':bool(valid and fresh),'observation_valid':valid,'fresh':fresh,
    'status':('SIMULATED · '+status) if packet.get('source_mode')=='SIMULATION' else status,'source_mode':packet.get('source_mode','HARDWARE'),'sensor_type':s.get('sensor_type','Not configured'),'values':s.get('values',{}),
    'processed_by_ml':bool(model_used),'used_by_rules':fresh and valid,'used_by_edge_ml':bool(fresh and valid and packet.get('local_brain',{}).get('ml_valid')),'diagnostic':s.get('diagnostic','')})
 return result
