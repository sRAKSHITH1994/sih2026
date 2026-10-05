from __future__ import annotations
from collections import defaultdict,deque
from datetime import datetime,timezone
from pathlib import Path
import math,time,json
import joblib
from .config import PROJECT_ROOT
from threadpoolctl import threadpool_limits
import numpy as np
from .config import CORE_FEATURES,CORE_TP_FEATURES,MODEL_TP_PATH,MODEL_TPH_PATH
from .lstm_autoencoder import NumpyLSTMAutoencoder
from .sensor_registry import flatten_sensor_values
from .spatial import SpatialVerifier

EQUIPMENT={'ELECTRICAL','MECHANICAL','STATION_DEGRADATION','STATION_TILTED','STATION_FALLEN','RAIN_BLOCKED','WIND_SEIZED','VANE_STUCK'}
ATMOSPHERIC={'SPIKE','DRIFT','FROZEN','ERRATIC','RAPID_CHANGE'}

class GlobalBrainEngine:
 def __init__(self,model_path=MODEL_TPH_PATH,tp_model_path=MODEL_TP_PATH):
  self.models={}
  for name,p in [('TPH',model_path),('TP',tp_model_path)]:
   if Path(p).exists():
    m=NumpyLSTMAutoencoder.load(p)
    if m.trained:self.models[name]=m
  self.second_opinion=None
  second_metadata=PROJECT_ROOT/'backend/models/edge_second_opinion.json'
  if second_metadata.exists() and json.loads(second_metadata.read_text()).get('enabled'):
   self.second_opinion=joblib.load(PROJECT_ROOT/'backend/models/edge_second_opinion.joblib')
  self.model=self.models.get('TPH');self.spatial=SpatialVerifier();self.states={};self.baselines=defaultdict(lambda:deque(maxlen=60))
 def reset(self):self.states.clear();self.baselines.clear();self.spatial.reset()
 def reset_station(self,station_id,source_mode=None):
  for key in list(self.states):
   if key[1]==station_id and (source_mode is None or key[0]==source_mode):self.states.pop(key,None);self.baselines.pop(key,None)
  for key in list(self.spatial.latest):
   if key[1]==station_id and (source_mode is None or key[0]==source_mode):self.spatial.latest.pop(key,None)
 def _state(self,key):
  return self.states.setdefault(key,{'bucket':None,'last':{},'last_at':None,'history':{'TP':deque(maxlen=20),'TPH':deque(maxlen=20)},'report':None})
 def _temporal(self,key,values,when):
  s=self._state(key);interval=int(next(iter(self.models.values())).sample_interval_seconds) if self.models else 60
  bucket=int(when.timestamp())//interval;complete=all(k in values for k in CORE_TP_FEATURES)
  new_window=False
  if s['bucket'] is not None and bucket>s['bucket']:
   old=s['last'];gap=bucket-s['bucket']
   if gap!=1 or s['last_at'] is None or s['bucket']*interval+interval-s['last_at']>max(5,interval*.2):
    for h in s['history'].values():h.clear()
    s['report']=None
   elif all(k in old for k in CORE_TP_FEATURES):
    s['history']['TP'].append([old[k] for k in CORE_TP_FEATURES])
    if all(k in old for k in CORE_FEATURES):s['history']['TPH'].append([old[k] for k in CORE_FEATURES])
    else:s['history']['TPH'].clear()
    new_window=True
  if s['bucket'] is None or bucket>=s['bucket']:
   s['bucket']=bucket;s['last']=dict(values);s['last_at']=when.timestamp()
  if not complete:
   for h in s['history'].values():h.clear()
   s['report']=None
  tph=self.models.get('TPH');tp=self.models.get('TP')
  tph_ready=tph is not None and len(s['history']['TPH'])>=tph.sequence_length
  profile='TPH' if tph_ready else 'TP' if tp else 'TPH';model=self.models.get(profile);history=s['history'][profile]
  base={'ready':False,'profile':profile,'score':None,'anomaly':False,'loss':None,'threshold':model.threshold if model else None,
     'attribution':{},'shapley':{},'samples':len(history),'required_samples':model.sequence_length if model else 20,
     'sample_interval_seconds':interval,'tph_samples':len(s['history']['TPH'])}
  if not complete:base['reason']='Temperature/pressure unavailable; sequence reset.';return base
  if not model:base['reason']='Trained temporal model unavailable.';base['unavailable']=True;return base
  if len(history)<model.sequence_length:base['reason']=f'{profile}: {len(history)}/{model.sequence_length} completed {interval}-second observations. Local checks remain active.';return base
  if new_window or s['report'] is None or s['report'].get('profile')!=profile:
   window=np.asarray(history,dtype=np.float32);r=dict(base);r.update(model.score(window));r['profile']=profile
   r['shapley']=model.exact_shapley(window) if r['anomaly'] else {}
   scaled=(window-model.mean)/model.std;reconstruction=model._forward(scaled[None])[0][0]*model.std+model.mean
   r['reconstruction']={name:float(reconstruction[-1,i]) for i,name in enumerate(model.feature_names)}
   r['observed']={name:float(window[-1,i]) for i,name in enumerate(model.feature_names)}
   r['evaluated_at']=when.isoformat();r['reason']='Reconstruction error exceeds validation threshold.' if r['anomaly'] else 'Minute sequence within validation threshold.';s['report']=r
  return dict(s['report'])
 def _second_opinion(self,local):
  f=local.get('feature_vector')
  if self.second_opinion is None or not local.get('ml_valid') or f is None or len(f)!=56 or not np.isfinite(f).all():
   return {'available':False,'reason':'Validated raw edge feature vector or selected model unavailable.'}
  from .local_reference import weights
  from inference import infer,gate
  x=np.asarray(f,dtype=np.float32)
  if x[48]<.5:return {'available':False,'reason':'BMP mask invalid'}
  with threadpool_limits(limits=1):p=gate(self.second_opinion.predict_proba(x[None])[0],x)
  edge=infer(x,weights());combined=.5*(edge+p);cls=int(combined.argmax())
  return {'available':True,'class_id':cls,'class_name':__import__('feature_pipeline').CLASS_NAMES[cls],
          'model_score':float(combined[cls]),'boosting_score':float(p.max()),'blend_weight':.5,'calibrated_probability':False,
          'uses':'Firmware 1 Hz 56-feature vector; never reconstruct a 1 Hz window from slower HTTP delivery.'}
 @staticmethod
 def _multivariate(values):
  ranges={'temperature_c':(-50,85),'pressure_hpa':(300,1100),'humidity_pct':(0,100)};bad=[k for k,(lo,hi) in ranges.items() if k in values and not lo<=values[k]<=hi]
  return {'consistent':not bad,'invalid_features':bad,'explanation':'Outside configured physical sensor range: '+', '.join(bad) if bad else 'Available channels pass physical range checks. This is not proof of meteorological consistency.'}
 def process(self,packet,received_at=None):
  start=time.perf_counter();when=received_at or datetime.now(timezone.utc)
  station=packet['station_id'];mode=packet.get('source_mode','HARDWARE');key=(mode,station,packet.get('boot_id','legacy'))
  values,active=flatten_sensor_values(packet);local=packet.get('local_brain',{});fault=local.get('fault_type','NORMAL').upper()
  temporal=self._temporal(key,values,when);physical=self._multivariate(values)
  invalid=[]
  for k,s in packet.get('sensors',{}).items():
   configured=s.get('configured',s.get('attached',False))
   if configured and (not s.get('attached') or not s.get('valid') or k not in active):invalid.append(k)
  core=all(k in values for k in CORE_TP_FEATURES)
  second=self._second_opinion(local)
  local_alert=bool(local.get('anomaly'))
  # Continuous evidence fusion. Physical/rule faults retain precedence; the LSTM
  # never gates out an edge alarm. Scores are not calibrated probabilities.
  loss=temporal.get('loss');threshold=temporal.get('threshold')
  ratio=float(loss)/max(float(threshold),1e-12) if temporal.get('ready') and loss is not None and threshold else 0.
  temporal_strength=ratio/(1.+ratio)
  edge_strength=float(local.get('ml_probability') or 0) if local.get('ml_valid') and local.get('ml_class',0)!=0 else 0.
  if second.get('available'):
   edge_strength=float(second['model_score']) if second['class_id'] else 0.
  fused_strength=1.-(1.-edge_strength)*(1.-temporal_strength)
  model_alert=bool(temporal.get('ready') and fused_strength>=.65)
  server_alert=bool(second.get('available') and second['class_id'] and second['model_score']>=.8)
  if server_alert and not local_alert:fault=second['class_name']
  fusion={'edge_fault_score':edge_strength,'lstm_loss_ratio':ratio if temporal.get('ready') else None,
          'lstm_continuous_strength':temporal_strength,'combined_evidence_score':fused_strength,
          'alert_threshold':.65,'calibrated_probability':False,'available':bool(temporal.get('ready') or local.get('ml_valid'))}

  equipment=(local_alert or server_alert) and fault in EQUIPMENT
  pose=local.get('station_position',{});position=bool(pose.get('active') and pose.get('calibrated'))
  changes={};history=self.baselines[key]
  if len(history)>=20:
   for name,minimum in [('temperature_c',.5),('pressure_hpa',.8),('humidity_pct',3.)]:
    previous=[v[name] for v in history if name in v]
    if name in values and len(previous)>=20:
     delta=values[name]-float(np.median(previous))
     if abs(delta)>=minimum:changes[name]=delta
  atmospheric=((local_alert or server_alert) and fault in ATMOSPHERIC) or model_alert
  spatial=self.spatial.analyze(station,values,packet.get('latitude'),packet.get('longitude'),when,mode,changes)
  weather=atmospheric and not equipment and not position and not invalid and physical['consistent'] and spatial.corroborated
  affected=list(dict.fromkeys(local.get('affected_sensors',[])+invalid+physical['invalid_features']))
  d={'category':'NORMAL','specific_type':'NORMAL','anomaly':False,'genuine_weather':False,'sensor_fault':False,'communication_fault':False,
     'confidence':0.0,'confidence_available':False,'confidence_kind':'not_calibrated','severity':'NORMAL','affected_features':affected,
     'readiness':'READY' if temporal.get('ready') else 'MODEL_UNAVAILABLE' if temporal.get('unavailable') else 'WARMING_UP'}
  if position:
   d.update(category='STATION_POSITION_FAULT',specific_type='STATION_FALLEN' if pose.get('critical') else 'STATION_TILTED',anomaly=True,
     severity='CRITICAL' if pose.get('critical') or invalid else 'HIGH',sensor_fault=bool(invalid),explanation=local.get('explanation','Station is outside its calibrated orientation tolerance.'))
  elif invalid or not physical['consistent'] or (local_alert and fault=='DATA_LOSS'):
   d.update(category='SENSOR_FAULT',specific_type='DATA_LOSS' if invalid or fault=='DATA_LOSS' else 'PHYSICAL_RANGE',anomaly=True,sensor_fault=True,severity='CRITICAL',explanation='Unavailable or invalid configured measurements: '+', '.join(affected))
  elif local_alert and fault=='COMMUNICATION_FAULT':
   d.update(category='COMMUNICATION_FAULT',specific_type=fault,anomaly=True,communication_fault=True,severity='HIGH',explanation=local.get('explanation','Telemetry backlog requires attention.'))
  elif equipment:
   d.update(category='EQUIPMENT_FAULT',specific_type=fault,anomaly=True,severity=local.get('severity_level','HIGH'),explanation=local.get('explanation','Equipment evidence requires inspection.'))
  elif weather:
   d.update(category='GENUINE_WEATHER_EVENT',specific_type='SPATIOTEMPORAL_EVENT',anomaly=True,genuine_weather=True,severity='HIGH',explanation=spatial.explanation)
  elif atmospheric or local_alert or server_alert:
   direct=fault in {'FROZEN','SPIKE','ERRATIC'} and local_alert
   d.update(category='SENSOR_FAULT' if direct else 'UNVERIFIED_ANOMALY',specific_type=fault if fault!='NORMAL' else 'TEMPORAL_ANOMALY',anomaly=True,
     sensor_fault=direct,severity='HIGH' if direct else 'WARNING',explanation=(local.get('explanation') if direct else 'Atmospheric anomaly detected; weather versus sensor fault remains uncertain. '+spatial.explanation))
  elif not core:d.update(category='NO_DATA',specific_type='NO_VALID_CORE_DATA',severity='INFO',explanation='No valid temperature/pressure evidence; no normality claim.')
  elif not temporal.get('ready'):
   d.update(category=d['readiness'],specific_type=d['readiness'],severity='INFO',explanation=temporal['reason'])
  else:d['explanation']='Available local and temporal checks found no anomaly. Spatial corroboration is only used when a weather change occurs.'
  d['evidence']={'second_opinion':second,'fusion':fusion,'local_brain':local,'lstm':temporal,'spatial':spatial.to_dict(),'multivariate':physical,'active_sensors':active,
     'active_features':sorted(values),'xai':{'local_edge_method':'gradient_x_input','local_edge_features':local.get('ml_top_features',''),
      'global_method':temporal.get('shapley',{}).get('method','not_run'),'global_importance':temporal.get('shapley',{}).get('importance',{})},
     'weather_change':changes,'model':'trained 56-feature 10-class MLP + 60s_LSTM + source-isolated spatial evidence'}
  d['explanation']+=' Confidence is unavailable; health index and model scores are uncalibrated evidence.'
  self.spatial.update(station,values,packet.get('latitude'),packet.get('longitude'),when,atmospheric,mode,changes,equipment or position or bool(invalid))
  # Retain a protected baseline during an atmospheric alert, then allow recovery.
  if not atmospheric or len(history)<20:history.append(values)
  return d,(time.perf_counter()-start)*1000
