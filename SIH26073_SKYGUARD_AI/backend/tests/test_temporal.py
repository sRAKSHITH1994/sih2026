from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
from app.global_brain import GlobalBrainEngine
from app.schemas import TelemetryPacket
from test_api import sample_packet

def test_missing_models_or_warmup_never_certifies_normal():
 e=GlobalBrainEngine('/does/not/exist','/does/not/exist');p=TelemetryPacket.model_validate(sample_packet()).model_dump(mode='json');d,_=e.process(p)
 assert d['category']=='MODEL_UNAVAILABLE' and d['confidence']==0 and not d['confidence_available']

def test_minute_cadence_tp_to_tph_transition_and_gap_reset():
 e=GlobalBrainEngine();key=('HARDWARE','T','B');base=datetime(2025,1,1,tzinfo=timezone.utc)
 v={'temperature_c':28.,'pressure_hpa':1008.}
 for sec in range(60):r=e._temporal(key,v,base+timedelta(seconds=sec))
 assert not r['ready'] and r['samples']==0
 for minute in range(1,21):
  r=e._temporal(key,v,base+timedelta(seconds=minute*60))
  e._temporal(key,v,base+timedelta(seconds=minute*60+59))
 assert r['ready'] and r['profile']=='TP'
 humid={**v,'humidity_pct':65.}
 r=e._temporal(key,humid,base+timedelta(seconds=21*60))
 assert r['ready'] and r['profile']=='TP' # new humidity does not disable ready TP
 for minute in range(21,42):
  e._temporal(key,humid,base+timedelta(seconds=minute*60+59));r=e._temporal(key,humid,base+timedelta(seconds=(minute+1)*60))
 assert r['ready'] and r['profile']=='TPH'
 r=e._temporal(key,humid,base+timedelta(seconds=46*60))
 assert not r['ready'] and r['samples']==0

def test_training_never_stitches_across_labelled_anomalies_or_gaps(tmp_path):
 import importlib.util,pandas as pd
 path=Path(__file__).resolve().parents[2]/'scripts/train_lstm.py';spec=importlib.util.spec_from_file_location('train_lstm',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 timestamps=pd.date_range('2025-01-01',periods=80,freq='min',tz='UTC').to_list();timestamps[40:]=[t+timedelta(minutes=5) for t in timestamps[40:]]
 df=pd.DataFrame({'timestamp':timestamps,'temperature':np.arange(80),'pressure':1000+np.arange(80),'humidity':60,'anomaly':0});df.loc[20,'anomaly']=1
 p=tmp_path/'data.csv';df.to_csv(p,index=False);windows,_=module.windows(p,['temperature_c','pressure_hpa'])
 assert len(windows)>0
 for w in windows:
  assert np.all(np.diff(w[:,0])==1);assert 20 not in w[:,0];assert not (w[0,0]<40<=w[-1,0])


def test_simulation_reset_does_not_reset_same_named_hardware():
 e=GlobalBrainEngine();hardware=('HARDWARE','SIM_AWS_01','boot');sim=('SIMULATION','SIM_AWS_01','boot')
 e._state(hardware);e._state(sim);e.reset_station('SIM_AWS_01','SIMULATION')
 assert hardware in e.states and sim not in e.states
