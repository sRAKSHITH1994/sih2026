from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json,hashlib,subprocess
import numpy as np
import pytest
from test_api import sample_packet,send
from app.main import app
from fastapi.testclient import TestClient
from corpus import session
from feature_pipeline import CLASS_NAMES,FEATURE_NAMES,FeatureExtractor
from inference import infer
ROOT=Path(__file__).resolve().parents[2]


def test_frontend_entire_tree_byte_identical():
    expected=json.loads((ROOT/'docs/frontend_original_sha256.json').read_text())
    actual={p.relative_to(ROOT/'frontend').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'frontend').rglob('*') if p.is_file()}
    assert actual==expected


def test_original_api_routes_and_safe_display_contract(client,auth):
    p=sample_packet();p['sensors']['humidity']['valid']=False;p['sensors']['humidity']['values']['humidity_pct']=0
    send(client,auth,p)
    station=client.get('/api/v1/stations').json()['stations'][0]
    h=station['packet']['sensors']['humidity'];assert h['values']['humidity_pct']=='—'
    assert h['observations']['humidity_pct'] is None and not h['available']
    assert h['raw_values']['humidity_pct']==0
    from app.main import legacy_report
    stale=legacy_report({'packet':p},stale=True)['packet']
    assert stale['sensors']['bmp280']['observations']['temperature_c'] is None
    assert stale['local_brain']['ml_class_name']=='STALE' and not stale['local_brain']['ml_probability_available']
    lstm=station['decision']['evidence']['lstm'];assert lstm['loss']=='—' and lstm['loss_value'] is None
    hist=client.get('/api/v1/stations/TEST_NODE/history').json();assert hist['station_id']=='TEST_NODE'
    hw=client.get('/api/v1/stations/TEST_NODE/hardware').json();assert {'firmware_version','link','last_report','sensors'}<=hw.keys()
    assert isinstance(hw['sensors'],list)
    for path in ['/api/v1/health','/api/v1/architecture','/api/v1/simulation/scenarios']:
        assert client.get(path).status_code==200
    scenarios=client.get('/api/v1/simulation/scenarios').json()['scenarios'];assert 'station_power_failure' in scenarios
    # Literal ORIGINAL JS formatter proves why null is forbidden in legacy display values.
    if __import__('shutil').which('node'):
        code="const fmt=v=>Number.isFinite(Number(v))?Number(v).toFixed(1):'—'; if(fmt('—')!=='—'||fmt(null)!=='0.0')process.exit(1)"
        subprocess.run(['node','-e',code],check=True)


def test_loopback_dashboard_write_session_and_cross_site_rejection():
    with TestClient(app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',45678)) as c:
        assert c.post('/api/v1/simulation/step',json={}).status_code==401
        page=c.get('/');assert page.status_code==200 and 'sih_dashboard' in c.cookies
        r=c.post('/api/v1/simulation/step',json={'scenario':'normal','reset':True});assert r.status_code==200,r.text
        assert {'scenario','generated_packets','simulation_index','target'}<=r.json().keys()
        assert c.post('/api/v1/simulation/step',headers={'Origin':'https://evil.invalid'},json={}).status_code==403
        assert c.post('/api/v1/reset').status_code==401
        assert c.post('/api/v1/telemetry',json=sample_packet()).status_code==401
    with TestClient(app,base_url='http://evil.invalid',client=('127.0.0.1',12345)) as c:
        c.get('/');assert 'sih_dashboard' not in c.cookies


def test_simulated_hardware_is_explicit_and_not_missing(client,auth):
    response=client.post('/api/v1/simulation/step',headers=auth,json={'scenario':'normal','reset':True}).json()
    local=response['target']['packet']['local_brain']
    assert local['health_index'] is None and not local['health_index_available'] and local['risk_kind']=='not_simulated'
    h=client.get('/api/v1/stations/SIM_AWS_01/hardware').json()
    assert h['source_mode']=='SIMULATION'
    assert all(s['status'].startswith('SIMULATED') for s in h['sensors'])
    assert client.get('/api/v1/stations/SIM_AWS_01/history').json()['history']


def test_unavailable_classes_remain_in_model_but_are_gated():
    with np.load(ROOT/'edge_training/artifacts/edge_mlp.npz') as z:w=dict(z)
    assert list(w['classes'])==CLASS_NAMES and len(FEATURE_NAMES)==56 and w['w3'].shape[1]==10
    f=np.zeros(56,np.float32);f[48]=1
    p=infer(f,w)
    assert np.all(p[5:]==0) and np.isclose(p.sum(),1)


def test_spike_labels_only_altered_samples_and_persistent_recovery_normal():
    frame,y,meta=session(1,9999)
    marked=np.zeros(len(frame),bool)
    for e in meta['events']:
        assert 1<=e['end']-e['start']<=2;marked[e['start']:e['end']]=True
    np.testing.assert_array_equal(y!=0,marked)
    for cls in range(2,10):
        _,y,m=session(cls,9999+cls)
        assert np.all(y[:m['onset']]==0) and np.all(y[m['onset']:m['end']]==cls) and np.all(y[m['end']:]==0)


def test_feature_gap_reset_missing_mask_never_fabricates_observation():
    raw,_,_=session(0,551);fex=FeatureExtractor()
    rows=raw.to_dict('records')
    for r in rows[:25]:fex.push(r)
    r=dict(rows[25],timestamp_ms=40000,bmp_valid=0,temperature_c=50,pressure_hpa=1080)
    f=fex.push(r);assert len(fex.history)==1 and f[0]==f[4]==f[48]==0


def test_equipment_fault_precedes_spatial_weather():
    from app.global_brain import GlobalBrainEngine
    from app.schemas import TelemetryPacket
    e=GlobalBrainEngine();now=datetime.now(timezone.utc)
    for ident in ['N1','N2','TARGET']:
        p=sample_packet();p['station_id']=ident;p['local_brain'].update(anomaly=True,fault_type='MECHANICAL')
        d,_=e.process(TelemetryPacket.model_validate(p).model_dump(mode='json'),now)
        assert d['category']=='EQUIPMENT_FAULT' and not d['genuine_weather']


def test_continuous_lstm_fusion_without_threshold_gate():
    from app.global_brain import GlobalBrainEngine
    from app.schemas import TelemetryPacket
    e=GlobalBrainEngine();e.second_opinion=None
    p=sample_packet();p['local_brain'].update(ml_valid=True,ml_class=2,ml_probability=.7)
    p=TelemetryPacket.model_validate(p).model_dump(mode='json')
    e._temporal=lambda *a:{'ready':True,'loss':.8,'threshold':1.,'anomaly':False,'reason':'subthreshold','shapley':{}}
    d,_=e.process(p)
    assert d['anomaly'] and d['evidence']['fusion']['lstm_loss_ratio']==.8
    assert not d['evidence']['lstm']['anomaly'] # Continuous score participates even below hard threshold.


def test_original_frontend_evaluation_request_is_still_valid():
    from app.schemas import EvaluationRequest
    r=EvaluationRequest(samples_per_scenario=100,stations=5,seed=42);assert r.samples_per_scenario==100


def test_all_split_manifests_disjoint_by_whole_session():
    for path in (ROOT/'edge_training/artifacts/experiments').glob('seed_*/split_manifest.json'):
        m=json.loads(path.read_text());seeds=[{g['seed'] for g in m[k]} for k in ['train','validation','test']]
        assert not seeds[0]&seeds[1] and not seeds[0]&seeds[2] and not seeds[1]&seeds[2]
