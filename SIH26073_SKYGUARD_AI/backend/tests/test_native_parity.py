"""Runs real firmware feature/ML/rule code on host (no hardware IO is mocked as tested)."""
import shutil,subprocess
from pathlib import Path
import numpy as np
import pytest
from app.local_reference import LocalReference,CLASS_NAMES
from app.simulator import packet_from_row
from datetime import datetime,timezone,timedelta
from corpus import session
ROOT=Path(__file__).resolve().parents[2]
@pytest.fixture(scope='module')
def native(tmp_path_factory):
 if not shutil.which('g++'):pytest.skip('g++ required for native parity; full ESP32 build is a separate gate')
 binary=tmp_path_factory.mktemp('native')/'replay'
 subprocess.run(['g++','-std=c++17','-O2','-I'+str(ROOT/'firmware/tests/native_stub'),'-I'+str(ROOT/'firmware/include'),str(ROOT/'firmware/tests/native_replay.cpp'),str(ROOT/'firmware/src/feature_engine.cpp'),str(ROOT/'firmware/src/edge_mlp.cpp'),'-o',str(binary)],check=True,capture_output=True)
 return binary
@pytest.mark.parametrize('class_id',range(10))
def test_cpp_features_model_and_rules_match_reference(native,class_id):
 frame,_,_=session(class_id,440000+class_id,140)
 columns=['timestamp_ms','temperature_c','pressure_hpa','humidity_pct','ax','ay','az','gx','gy','gz','bus_voltage_v','current_ma','power_mw','rain_rate_mm_h','wind_speed_ms','wind_direction_deg','solar_wm2',*[k+'_valid' for k in ['bmp','humidity','mpu','ina','rain','wind','vane','solar']]]
 raw=frame[columns].to_numpy(dtype=np.float32);text='\n'.join(' '.join(str(int(v)) if j==0 else f'{v:.9g}' for j,v in enumerate(r)) for r in raw)+'\n'
 cpp=np.loadtxt(subprocess.run([str(native)],input=text,text=True,capture_output=True,check=True).stdout.splitlines())
 ref=LocalReference();origin=datetime(2025,1,1,tzinfo=timezone.utc);features=[];pred=[];rules=[]
 for i,row in enumerate(frame.astype(np.float32).to_dict('records')):
  p=packet_from_row(row,'N',i,'B',origin+timedelta(seconds=i));report=ref.evaluate(p);pred.append(report)
  # Features already extracted exactly once by evaluate().
  from feature_pipeline import FeatureExtractor
 # independent feature sequence to check numerical preprocessing
 fex=FeatureExtractor();rule_ref=LocalReference()
 for i,row in enumerate(frame.astype(np.float32).to_dict('records')):
  f=fex.push(row);features.append(f);fault=rule_ref.rules(f,i>=19)[0];rules.append(CLASS_NAMES.index(fault))
 np.testing.assert_allclose(cpp[:,4:60],features,rtol=.002,atol=.002)
 np.testing.assert_array_equal(cpp[:,3],rules)
 assert np.array_equal(cpp[19:,1],[r['ml_class'] for r in pred[19:]])
 np.testing.assert_allclose(cpp[19:,2],[r['ml_probability'] for r in pred[19:]],atol=.005,rtol=.005)

def test_position_state_machine(tmp_path):
 if not shutil.which('g++'):pytest.skip('g++ unavailable')
 binary=tmp_path/'position';subprocess.run(['g++','-std=c++17','-I'+str(ROOT/'firmware/include'),str(ROOT/'firmware/tests/test_position.cpp'),'-o',str(binary)],check=True,capture_output=True)
 subprocess.run([str(binary)],check=True,capture_output=True)

def test_recovery_retries_and_trusted_baseline_rejection(tmp_path):
 if not shutil.which('g++'):pytest.skip('g++ unavailable')
 binary=tmp_path/'recovery';subprocess.run(['g++','-std=c++17','-I'+str(ROOT/'firmware/tests/native_stub'),'-I'+str(ROOT/'firmware/include'),str(ROOT/'firmware/tests/test_recovery_trusted.cpp'),str(ROOT/'firmware/src/recovery_manager.cpp'),str(ROOT/'firmware/src/trusted_data.cpp'),'-o',str(binary)],check=True,capture_output=True)
 subprocess.run([str(binary)],check=True,capture_output=True)
