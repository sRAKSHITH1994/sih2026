"""Executable host reference of firmware feature/ML/rule path; never reads labels.
Hardware recovery, trusted-value and alarm state machines run only on the ESP32.
"""
from pathlib import Path
import sys,ctypes,os,shutil
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'edge_training'))
from feature_pipeline import FeatureExtractor,FEATURE_NAMES,CLASS_NAMES
from .schemas import EXPECTED

KEYS=['bmp280','humidity','mpu6050','ina219','rain','wind','vane','solar']
SHORT=['bmp','humidity','mpu','ina','rain','wind','vane','solar']
RENAMES=dict(zip(EXPECTED['mpu6050'],['ax','ay','az','gx','gy','gz']))
WEIGHTS=None

def weights():
 global WEIGHTS
 if WEIGHTS is None:
  with np.load(ROOT/'edge_training/artifacts/edge_mlp.npz',allow_pickle=False) as f:WEIGHTS={k:f[k] for k in f.files}
 return WEIGHTS

def infer(f):
 from inference import infer as exported_infer
 w=weights();p=exported_infer(f,w);cls=int(p.argmax())
 x=(f-w['mean'])/w['scale'];h1=np.maximum(0,x@w['w1']+w['b1']);h2=np.maximum(0,h1@w['w2']+w['b2'])
 grad=w['w1']@((h1>0)*(w['w2']@((h2>0)*w['w3'][:,cls])))
 top=np.argsort(-np.abs(x*grad),kind='stable')[:3]
 return cls,float(p[cls]),', '.join(FEATURE_NAMES[i] for i in top),p

class NativeRules:
 def __init__(self):
  path=ROOT/'firmware/tests/build'/('edge_rules.dll' if os.name=='nt' else 'libedge_rules.so')
  # Python on Windows no longer searches PATH for a DLL's dependent runtimes.
  compiler=shutil.which('g++') if os.name=='nt' else None
  if os.name=='nt' and compiler:
   with os.add_dll_directory(str(Path(compiler).parent)):self.lib=ctypes.CDLL(str(path))
  else:self.lib=ctypes.CDLL(str(path))
  self.lib.rules_create.restype=ctypes.c_void_p
  self.lib.rules_evaluate.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_float),ctypes.c_int,ctypes.c_float,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_float)]
  self.lib.rules_destroy.argtypes=[ctypes.c_void_p];self.handle=self.lib.rules_create()
 def evaluate(self,f,ready,nominal):
  f=np.ascontiguousarray(f,dtype=np.float32);cls=ctypes.c_int();severity=ctypes.c_float()
  self.lib.rules_evaluate(self.handle,f.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),ready,nominal,ctypes.byref(cls),ctypes.byref(severity))
  return cls.value,severity.value
 def __del__(self):
  if getattr(self,'handle',None):self.lib.rules_destroy(self.handle)

class LocalReference:
 def __init__(self,require_native=False):
  self.features=FeatureExtractor();self.frozen=0;self.last_ms=None;self.native=None
  try:self.native=NativeRules()
  except OSError:
   if require_native:raise RuntimeError('Run python scripts/build_native.py before the reproducible native-rule benchmark')
 def rules(self,f,ready,nominal=5.):
  choices=[('NORMAL',0,[],'No local fault detected.')]
  if f[48]>.5 and (abs(f[1])>4 or abs(f[5])>6 or (f[49]>.5 and abs(f[9])>15)):choices.append(('SPIKE',82,['bmp280','humidity'],'Abrupt raw measurement change.'))
  flat=ready and f[48]>.5 and f[2]<.012 and f[6]<.025
  self.frozen=self.frozen+1 if flat else 0
  if self.frozen>=5:choices.append(('FROZEN',78,['bmp280'],'Atmospheric readings remain flat across a complete window.'))
  if ready and f[48]>.5 and not flat and ((abs(f[3])>.045 and abs(f[30])>1) or (abs(f[7])>.075 and abs(f[31])>1)):choices.append(('DRIFT',66,['bmp280'],'Sustained slope and CUSUM departure.'))
  if f[50]>.5 and (f[13]>1.3 or abs(f[14])>1.8 or f[15]>2.8):choices.append(('MECHANICAL',70,['mpu6050'],'Motion or vibration exceeds configured limit.'))
  if f[51]>.5 and (f[16]<nominal*.89 or (ready and f[18]>.14) or abs(f[20])>70):choices.append(('ELECTRICAL',84,['ina219'],'Supply voltage or current departs from nominal rail.'))
  if self.native:
   cls,severity=self.native.evaluate(f,ready,nominal)
   # Native firmware determines the class and severity; the text is a description.
   matches=[r for r in choices if r[0]==CLASS_NAMES[cls]]
   if matches:return (CLASS_NAMES[cls],severity,matches[-1][2],matches[-1][3])
   return CLASS_NAMES[cls],severity,[],'Native firmware rule '+CLASS_NAMES[cls]
  return max(choices,key=lambda x:x[1])
 def evaluate(self,packet):
  ms=packet.get('uptime_ms',0)
  if self.last_ms is not None and (ms<self.last_ms or ms-self.last_ms>2500):self.features=FeatureExtractor();self.frozen=0;self.native=NativeRules() if self.native else None
  self.last_ms=ms;row={};bad=[]
  for key,short in zip(KEYS,SHORT):
   ch=packet['sensors'].get(key,{});v=ch.get('values',{})
   valid=ch.get('attached',False) and ch.get('valid',False) and all(v.get(k) is not None and np.isfinite(v[k]) for k in EXPECTED[key])
   row[short+'_valid']=int(valid)
   for name in EXPECTED[key]:
    value=v.get(name);row[RENAMES.get(name,name)]=float(value) if value is not None and np.isfinite(value) else 0.
   if ch.get('configured',ch.get('attached',False)) and not valid:bad.append(key)
  row['timestamp_ms']=ms
  f=self.features.push(row);self.last_features=f;ready=len(self.features.history)==20 and all(r['bmp_valid'] for r in self.features.history)
  cls,prob,top,_=infer(f) if ready else (0,None,'',None)
  fault,severity,affected,reason=self.rules(f,ready)
  if ready and cls and prob>=.80 and 40+prob*40>severity:
   fault=CLASS_NAMES[cls];severity=40+prob*40;affected={5:['ina219'],6:['mpu6050'],7:['rain'],8:['wind'],9:['vane']}.get(cls,['bmp280','humidity']);reason='Edge MLP detects '+fault+'. Strongest attributions: '+top
  if bad:fault,severity,affected,reason='DATA_LOSS',90,bad,'Configured sensor has missing or invalid measurements: '+', '.join(bad)
  return {'anomaly':severity>0,'fault_type':fault,'severity_score':severity,'severity_level':'CRITICAL' if severity>=80 else 'HIGH' if severity>=60 else 'NORMAL',
   'confidence':0.0,'confidence_available':False,'confidence_kind':'not_calibrated','explanation':reason,'affected_sensors':affected,
   'warmup_complete':ready,'ml_valid':ready,'ml_class':cls,'ml_probability':prob,'ml_class_name':CLASS_NAMES[cls] if ready else 'WARMUP','ml_top_features':top,
   'feature_vector':f.tolist(),'ewma_score':float(min(100,max(abs(f[27:30]))*20)),'cusum_score':float(min(100,max(abs(f[30:33]))*100)),
   'station_state':'LOCAL_ALERT' if severity else 'LOCAL_CHECKS_CLEAR','alarm_state':'RED' if severity>=80 else 'YELLOW' if severity else 'GREEN','failure_risk_score':0,'health_index':None,'risk_kind':'not_simulated','maintenance_action':'Inspect '+fault+' evidence.' if severity else 'Host replica: physical health/recovery/pose are not simulated.', 'implementation':'host_reference_features_mlp_native_rules' if self.native else 'host_reference_features_mlp_parity_verified_python_rules'}
