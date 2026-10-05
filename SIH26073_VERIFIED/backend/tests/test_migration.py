import sqlite3,json
from datetime import datetime,timezone,timedelta
from app.storage import Storage
from test_api import sample_packet

def test_legacy_database_backfill_preserves_reports_and_is_idempotent(tmp_path):
 path=tmp_path/'old.db';c=sqlite3.connect(path)
 c.executescript('CREATE TABLE reports(id INTEGER PRIMARY KEY AUTOINCREMENT,received_at TEXT NOT NULL,station_id TEXT NOT NULL,packet_json TEXT NOT NULL,decision_json TEXT NOT NULL,inference_ms REAL NOT NULL);')
 now=datetime.now(timezone.utc)
 for i,anomaly in enumerate([True,True,False,True]):
  p=sample_packet(i,when=now+timedelta(seconds=i));d={'anomaly':anomaly,'category':'SENSOR_FAULT' if anomaly else 'NORMAL','specific_type':'DATA_LOSS' if anomaly else 'NORMAL','severity':'HIGH','explanation':'legacy'}
  c.execute('INSERT INTO reports(received_at,station_id,packet_json,decision_json,inference_ms) VALUES(?,?,?,?,?)',(p['timestamp'],p['station_id'],json.dumps(p),json.dumps(d),1.))
 c.commit();c.close();store=Storage(path);store.initialize();store.initialize()
 assert len(store.recent('TEST_NODE'))==4
 e=store.events();assert e['total']==2 and all(r['status']=='HISTORICAL' for r in e['events'])
 assert sorted(r['sample_count'] for r in e['events'])==[1,2]
