from datetime import datetime,timezone,timedelta
from copy import deepcopy

def sample_packet(sequence=1,boot='test-boot',when=None):
 empty=lambda name:{'configured':False,'attached':False,'valid':False,'sensor_type':name,'values':{}}
 return {'station_id':'TEST_NODE','station_name':'Contract test','boot_id':boot,'timestamp':(when or datetime.now(timezone.utc)).isoformat(),'uptime_ms':sequence*1000,'sequence':sequence,
 'latitude':13.,'longitude':80.17,'firmware_version':'test','sensors':{
 'bmp280':{'configured':True,'attached':True,'valid':True,'sensor_type':'BMP280','values':{'temperature_c':28.2,'pressure_hpa':1009.8}},
 'humidity':{'configured':True,'attached':True,'valid':True,'sensor_type':'DHT11','values':{'humidity_pct':67.1}},
 'mpu6050':{'configured':True,'attached':True,'valid':True,'sensor_type':'MPU6050','values':{'accel_x_ms2':0.,'accel_y_ms2':0.,'accel_z_ms2':9.81,'gyro_x_rads':0.,'gyro_y_rads':0.,'gyro_z_rads':0.}},
 'ina219':{'configured':True,'attached':True,'valid':True,'sensor_type':'INA219','values':{'bus_voltage_v':5.,'current_ma':105.,'power_mw':525.}},
 'rain':empty('TIPPING_BUCKET'),'wind':empty('ANEMOMETER'),'vane':empty('WIND_VANE'),'solar':empty('PYRANOMETER')},
 'local_brain':{'anomaly':False,'fault_type':'NORMAL','warmup_complete':True,'explanation':'No local fault.'},'link':{'type':'WIFI','queue_depth':0}}

def send(client,auth,p):
 r=client.post('/api/v1/telemetry',headers=auth,json=p);assert r.status_code==200,r.text;return r.json()
def test_ingest_history_and_presence_contract(client,auth):
 r=send(client,auth,sample_packet());assert r['decision']['category']=='WARMING_UP';assert r['decision']['confidence']==0 and not r['decision']['confidence_available']
 s=client.get('/api/v1/stations').json()['stations'][0];assert s['reporting']
 rain=next(s for s in client.get('/api/v1/stations/TEST_NODE/hardware').json()['sensors'] if s['key']=='rain')
 assert rain['status']=='Not configured' and not rain['processed_by_ml']
 assert len(client.get('/api/v1/stations/TEST_NODE/history').json()['history'])==1

def test_mutating_routes_require_token(client):
 for path,body in [('telemetry',sample_packet()),('reset',{}),('simulation/step',{}),('evaluation/run',{}),('anomalies/1/acknowledge',{})]:
  assert client.post('/api/v1/'+path,json=body).status_code==401

def test_static_traversal_and_frontend(client):
 assert client.get('/').status_code==200
 for path in ['/%2e%2e/VERSION.txt','/%2e%2e/%2e%2e/firmware/include/user_config.h','/assets/%2e%2e/%2e%2e/package.json','/VERSION.txt']:
  assert client.get(path).status_code==404

def test_optional_humidity_has_no_fake_zero(client,auth):
 p=sample_packet();p['sensors']['humidity']={'configured':False,'attached':False,'valid':False,'values':{}}
 r=send(client,auth,p);assert not r['decision']['anomaly'];assert 'humidity_pct' not in r['decision']['evidence']['active_features']

def test_duplicate_does_not_add_history_or_event_samples(client,auth):
 p=sample_packet();p['sensors']['mpu6050']['valid']=False
 a=send(client,auth,p);b=send(client,auth,p);assert b['duplicate'] and a['report_id']==b['report_id']
 events=client.get('/api/v1/anomalies').json();assert events['total']==1 and events['events'][0]['sample_count']==1

def test_old_and_out_of_order_packets_cannot_replace_live(client,auth):
 now=datetime.now(timezone.utc);send(client,auth,sample_packet(5,when=now))
 r=send(client,auth,sample_packet(4,when=now-timedelta(seconds=1)));assert r['ingest_reason']=='out_of_order'
 r=send(client,auth,sample_packet(6,when=now-timedelta(minutes=2)));assert r['ingest_reason']!='accepted'
 assert client.get('/api/v1/stations').json()['stations'][0]['packet']['sequence']==5

def test_unknown_time_is_archived_and_not_healthy(client,auth):
 p=sample_packet();del p['timestamp'];r=send(client,auth,p);assert r['ingest_reason']=='time_unverified'
 hw=client.get('/api/v1/stations/TEST_NODE/hardware').json();assert not hw['fresh'];assert all(not s['processed_by_ml'] for s in hw['sensors'])

def test_monotonic_age_and_reboot_identity(client,auth):
 p=sample_packet();del p['timestamp'];p['sample_age_ms']=1000
 a=send(client,auth,p);assert a['ingest_reason']=='accepted';assert send(client,auth,p)['duplicate']
 b=send(client,auth,sample_packet(0,boot='reboot'));assert not b['duplicate']

def test_missing_required_value_becomes_invalid(client,auth):
 p=sample_packet();p['sensors']['bmp280']['values']['temperature_c']=None
 r=send(client,auth,p);assert r['decision']['specific_type']=='DATA_LOSS'

def test_physical_range_overrides_normal_local_report(client,auth):
 p=sample_packet();p['sensors']['bmp280']['values']['temperature_c']=150
 r=send(client,auth,p);assert r['decision']['specific_type']=='PHYSICAL_RANGE' and r['decision']['anomaly']

def test_event_acknowledge_recovery_and_restart(client,auth):
 from app.storage import Storage,storage
 start=datetime.now(timezone.utc)-timedelta(seconds=5)
 p=sample_packet(1,when=start);p['sensors']['mpu6050']['valid']=False;send(client,auth,p)
 event=client.get('/api/v1/anomalies').json()['events'][0];ident=event['id']
 assert client.post(f'/api/v1/anomalies/{ident}/acknowledge',headers=auth).status_code==200
 for i in range(2,5):send(client,auth,sample_packet(i,when=start+timedelta(seconds=i)))
 fresh=Storage(storage.path);fresh.initialize();e=fresh.events()['events'][0]
 assert e['status']=='RECOVERED' and e['acknowledged'] and e['ended_at']
 csv=client.get('/api/v1/anomalies/export.csv');assert 'DATA_LOSS' in csv.text and csv.headers['content-type'].startswith('text/csv')

def test_simulation_runs_model_with_explicit_mode(client,auth):
 r=client.post('/api/v1/simulation/step',headers=auth,json={'scenario':'electrical','reset':True,'include_humidity':False,'steps':60});assert r.status_code==200,r.text
 p=r.json()['target']['packet'];assert p['source_mode']=='SIMULATION' and not p['sensors']['humidity']['configured']
 assert p['local_brain']['ml_valid'] and p['local_brain']['fault_type']=='ELECTRICAL'
 assert p['local_brain']['implementation'].startswith('host_reference')
 assert p['local_brain']['failure_risk_score']==0 # not a fabricated scenario failure probability

def test_health_profiles(client):
 h=client.get('/api/v1/health').json();assert set(h['model_profiles'])=={'TP','TPH'} and h['temporal_cadence_seconds']==60

def test_sim_and_hardware_same_id_stay_separate(client,auth):
 p=sample_packet();send(client,auth,p);p=deepcopy(p);p['source_mode']='SIMULATION';p['sensors']['mpu6050']['valid']=False;send(client,auth,p)
 assert len(client.get('/api/v1/stations').json()['stations'])==2
 assert client.get('/api/v1/anomalies?source_mode=HARDWARE').json()['total']==0
 assert client.get('/api/v1/anomalies?source_mode=SIMULATION').json()['total']==1

def test_older_boot_replay_does_not_replace_current_boot(client,auth):
 now=datetime.now(timezone.utc);send(client,auth,sample_packet(1,boot='new',when=now))
 r=send(client,auth,sample_packet(9,boot='old',when=now-timedelta(seconds=4)))
 assert r['ingest_reason']=='older_than_current_session'
 assert client.get('/api/v1/stations').json()['stations'][0]['packet']['boot_id']=='new'

def test_simulation_can_reset_virtual_time(client,auth):
 for _ in range(2):
  r=client.post('/api/v1/simulation/step',headers=auth,json={'scenario':'normal','reset':True,'steps':60})
  assert r.status_code==200 and r.json()['target']['ingest_reason']=='accepted'

def test_unverified_event_time_and_csv_formula_protection(client,auth):
 import csv,io
 p=sample_packet();del p['timestamp'];p['local_brain'].update(anomaly=True,fault_type=' \t=1+1',severity_level='HIGH',explanation='\t=1+1')
 send(client,auth,p);event=client.get('/api/v1/anomalies').json()['events'][0]
 assert event['status']=='HISTORICAL' and event['evidence']['timestamp_is_receipt_time'] is True
 row=next(csv.DictReader(io.StringIO(client.get('/api/v1/anomalies/export.csv').text)))
 assert row['specific_type'].startswith("'") and row['explanation'].startswith('Archived packet')
