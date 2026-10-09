from __future__ import annotations
import csv,io,json,sqlite3,threading,hashlib
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from .config import DB_PATH
SEVERITY={'INFO':0,'NORMAL':0,'LOW':1,'WARNING':2,'HIGH':3,'CRITICAL':4}
class Storage:
 def __init__(self,path=DB_PATH):self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._local=threading.local();self.lock=threading.RLock()
 def _connection(self):
  c=getattr(self._local,'connection',None)
  if c is None:
   c=sqlite3.connect(self.path,check_same_thread=False,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA journal_mode=WAL');self._local.connection=c
  return c
 @contextmanager
 def transaction(self):
  with self.lock:
   c=self._connection()
   try:yield c;c.commit()
   except Exception:c.rollback();raise
 def initialize(self):
  with self.transaction() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY AUTOINCREMENT,received_at TEXT NOT NULL,station_id TEXT NOT NULL,packet_json TEXT NOT NULL,decision_json TEXT NOT NULL,inference_ms REAL NOT NULL);
   CREATE INDEX IF NOT EXISTS ix_reports_station_time ON reports(station_id,id DESC);
   CREATE TABLE IF NOT EXISTS evaluations(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,result_json TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS anomaly_events(id INTEGER PRIMARY KEY AUTOINCREMENT,station_id TEXT NOT NULL,source_mode TEXT NOT NULL,specific_type TEXT NOT NULL,category TEXT NOT NULL,severity TEXT NOT NULL,started_at TEXT NOT NULL,last_seen TEXT NOT NULL,ended_at TEXT,status TEXT NOT NULL DEFAULT 'ACTIVE',sample_count INTEGER NOT NULL DEFAULT 1,clear_count INTEGER NOT NULL DEFAULT 0,acknowledged INTEGER NOT NULL DEFAULT 0,explanation TEXT NOT NULL,first_report_id INTEGER,last_report_id INTEGER,evidence_json TEXT NOT NULL DEFAULT '{}');
   CREATE INDEX IF NOT EXISTS ix_events_filter ON anomaly_events(source_mode,station_id,status,id DESC);''')
   columns={r[1] for r in c.execute('PRAGMA table_info(reports)')}
   for name,kind in [('identity','TEXT'),('source_mode','TEXT'),('boot_id','TEXT'),('sequence','INTEGER'),('sample_at','TEXT'),('live_eligible','INTEGER NOT NULL DEFAULT 0'),('ingest_reason','TEXT')]:
    if name not in columns:c.execute(f'ALTER TABLE reports ADD COLUMN {name} {kind}')
   c.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_report_identity ON reports(identity) WHERE identity IS NOT NULL')
   # Preserve old reports and metadata. Legacy timestamps are not silently certified fresh.
   for r in c.execute('SELECT id,packet_json FROM reports WHERE source_mode IS NULL').fetchall():
    p=json.loads(r['packet_json']);c.execute('UPDATE reports SET source_mode=?,boot_id=?,sequence=?,sample_at=?,ingest_reason=? WHERE id=?',(p.get('source_mode','HARDWARE'),p.get('boot_id','legacy'),p.get('sequence'),p.get('timestamp'),'legacy_import',r['id']))
   # One-time backfill: old alerts become historical records, never currently active alarms.
   c.execute('CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY,value TEXT)')
   if not c.execute("SELECT 1 FROM app_meta WHERE key='event_backfill_v4'").fetchone():
    episodes={}
    for r in c.execute('SELECT * FROM reports ORDER BY id').fetchall():
     d=json.loads(r['decision_json']);p=json.loads(r['packet_json']);key=(r['source_mode'],r['station_id'],d.get('specific_type','UNKNOWN'))
     if not d.get('anomaly'):
      episodes={k:v for k,v in episodes.items() if k[:2]!=key[:2]};continue
     moment=r['sample_at'] or r['received_at'];prior=episodes.get(key)
     if prior and 0<=(datetime.fromisoformat(moment.replace('Z','+00:00')).replace(tzinfo=timezone.utc)-datetime.fromisoformat(prior[1].replace('Z','+00:00')).replace(tzinfo=timezone.utc)).total_seconds()<=300:
      c.execute('UPDATE anomaly_events SET last_seen=?,ended_at=?,sample_count=sample_count+1,last_report_id=? WHERE id=?',(moment,moment,r['id'],prior[0]));episodes[key]=(prior[0],moment)
     else:
      cur=c.execute('INSERT INTO anomaly_events(station_id,source_mode,specific_type,category,severity,started_at,last_seen,ended_at,status,explanation,first_report_id,last_report_id,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (r['station_id'],r['source_mode'],key[2],d.get('category','UNKNOWN'),d.get('severity','WARNING'),moment,moment,moment,'HISTORICAL',d.get('explanation','Imported alert'),r['id'],r['id'],json.dumps(d.get('evidence',{}))));episodes[key]=(cur.lastrowid,moment)
    c.execute("INSERT INTO app_meta VALUES('event_backfill_v4','complete')")
 def find_identity(self,identity):
  r=self._connection().execute('SELECT * FROM reports WHERE identity=?',(identity,)).fetchone();return self._decode(r) if r else None
 def insert_report(self,packet,decision,inference_ms,identity=None,live=True,reason='accepted',received_at=None):
  received_at=received_at or datetime.now(timezone.utc).isoformat()
  with self.transaction() as c:
   row=c.execute('INSERT INTO reports(received_at,station_id,packet_json,decision_json,inference_ms,identity,source_mode,boot_id,sequence,sample_at,live_eligible,ingest_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
     (received_at,packet['station_id'],json.dumps(packet),json.dumps(decision),inference_ms,identity,packet.get('source_mode','HARDWARE'),packet.get('boot_id','legacy'),packet.get('sequence',0),packet.get('timestamp'),int(live),reason))
   ident=row.lastrowid
   if live:self._events(c,packet,decision,ident)
   elif decision.get('anomaly'):
    moment=packet.get('timestamp') or received_at
    c.execute('INSERT INTO anomaly_events(station_id,source_mode,specific_type,category,severity,started_at,last_seen,ended_at,status,explanation,first_report_id,last_report_id,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
     (packet['station_id'],packet.get('source_mode','HARDWARE'),decision['specific_type'],decision['category'],decision['severity'],moment,moment,moment,'HISTORICAL',decision['explanation'],ident,ident,json.dumps(decision.get('evidence',{}))))
   return ident
 def _events(self,c,p,d,report_id):
  station=p['station_id'];mode=p.get('source_mode','HARDWARE');moment=p.get('timestamp') or datetime.now(timezone.utc).isoformat()
  active=c.execute("SELECT * FROM anomaly_events WHERE station_id=? AND source_mode=? AND status='ACTIVE'",(station,mode)).fetchall()
  same=None
  for e in active:
   if d.get('anomaly') and e['specific_type']==d['specific_type']:same=e;continue
   # Model warm-up does not certify atmospheric recovery; fresh packet clears communication outage.
   local=d.get('evidence',{}).get('local_brain',{})
   local_clear=bool(local) and not local.get('anomaly') and (local.get('warmup_complete') or e['specific_type'] in {'DATA_LOSS','ELECTRICAL','MECHANICAL'})
   can_clear=d['category']=='NORMAL' or e['specific_type']=='NOT_REPORTING' or (local_clear and e['specific_type'] not in {'TEMPORAL_ANOMALY','SPATIOTEMPORAL_EVENT'})
   if can_clear:
    n=e['clear_count']+1
    c.execute('UPDATE anomaly_events SET clear_count=?,status=?,ended_at=? WHERE id=?',(n,'RECOVERED' if n>=3 else 'ACTIVE',moment if n>=3 else None,e['id']))
   elif e['clear_count']:c.execute('UPDATE anomaly_events SET clear_count=0 WHERE id=?',(e['id'],))
  if not d.get('anomaly'):return
  if same:
   severity=d['severity'] if SEVERITY.get(d['severity'],0)>SEVERITY.get(same['severity'],0) else same['severity']
   c.execute('UPDATE anomaly_events SET last_seen=?,sample_count=sample_count+1,clear_count=0,severity=?,explanation=?,last_report_id=?,evidence_json=? WHERE id=?',
     (moment,severity,d['explanation'],report_id,json.dumps(d.get('evidence',{})),same['id']))
  else:c.execute('INSERT INTO anomaly_events(station_id,source_mode,specific_type,category,severity,started_at,last_seen,explanation,first_report_id,last_report_id,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
     (station,mode,d['specific_type'],d['category'],d['severity'],moment,moment,d['explanation'],report_id,report_id,json.dumps(d.get('evidence',{}))))
 def record_offline(self,p):
  d={'anomaly':True,'category':'COMMUNICATION_FAULT','specific_type':'NOT_REPORTING','severity':'CRITICAL','explanation':'No fresh measurement received within the configured stale interval.','evidence':{}}
  with self.transaction() as c:
   found=c.execute("SELECT 1 FROM anomaly_events WHERE station_id=? AND source_mode=? AND specific_type='NOT_REPORTING' AND status='ACTIVE'",(p['station_id'],p.get('source_mode','HARDWARE'))).fetchone()
   if not found:self._events(c,{**p,'timestamp':datetime.now(timezone.utc).isoformat()},d,None)
 def recent(self,station_id,limit=120,source_mode=None):
  sql='SELECT * FROM reports WHERE station_id=?';args=[station_id]
  if source_mode:sql+=' AND source_mode=?';args.append(source_mode)
  rows=self._connection().execute(sql+' ORDER BY id DESC LIMIT ?',(*args,limit)).fetchall();return [self._decode(r) for r in reversed(rows)]
 def latest_by_station(self):
  rows=self._connection().execute('SELECT r.* FROM reports r JOIN (SELECT source_mode,station_id,MAX(id) latest FROM reports WHERE live_eligible=1 GROUP BY source_mode,station_id) x ON r.id=x.latest ORDER BY r.id DESC').fetchall()
  # For imported-only stations expose last archived state with its real age.
  archived=self._connection().execute('SELECT r.* FROM reports r JOIN (SELECT source_mode,station_id,MAX(id) latest FROM reports GROUP BY source_mode,station_id) x ON r.id=x.latest ORDER BY r.id DESC').fetchall()
  result={(r['source_mode'],r['station_id']):r for r in rows}
  for r in archived:result.setdefault((r['source_mode'],r['station_id']),r)
  return [self._decode(r) for r in result.values()]
 def latest_live(self,station,mode):
  r=self._connection().execute('SELECT * FROM reports WHERE station_id=? AND source_mode=? AND live_eligible=1 ORDER BY id DESC LIMIT 1',(station,mode)).fetchone();return self._decode(r) if r else None
 def latest_session(self,station,mode,boot):
  r=self._connection().execute('SELECT * FROM reports WHERE station_id=? AND source_mode=? AND boot_id=? AND live_eligible=1 ORDER BY sequence DESC LIMIT 1',(station,mode,boot)).fetchone();return self._decode(r) if r else None
 def events(self,station_id=None,source_mode=None,status=None,limit=100,offset=0):
  conditions=[];args=[]
  for k,v in [('station_id',station_id),('source_mode',source_mode),('status',status)]:
   if v:conditions.append(k+'=?');args.append(v)
  where=' WHERE '+' AND '.join(conditions) if conditions else ''
  c=self._connection();total=c.execute('SELECT COUNT(*) FROM anomaly_events'+where,args).fetchone()[0]
  rows=c.execute('SELECT * FROM anomaly_events'+where+' ORDER BY id DESC LIMIT ? OFFSET ?',(*args,limit,offset)).fetchall()
  return {'total':total,'events':[{**dict(r),'evidence':json.loads(r['evidence_json'])} for r in rows]}
 def acknowledge(self,ident):
  with self.transaction() as c:return c.execute('UPDATE anomaly_events SET acknowledged=1 WHERE id=?',(ident,)).rowcount>0
 def _decode(self,r):return {**dict(r),'packet':json.loads(r['packet_json']),'decision':json.loads(r['decision_json'])}
 def save_evaluation(self,result):
  with self.transaction() as c:c.execute('INSERT INTO evaluations(created_at,result_json) VALUES(?,?)',(datetime.now(timezone.utc).isoformat(),json.dumps(result)))
 def latest_evaluation(self):
  r=self._connection().execute('SELECT * FROM evaluations ORDER BY id DESC LIMIT 1').fetchone()
  if not r:return None
  result=json.loads(r['result_json'])
  return {**result,'created_at':r['created_at']} if result.get('provenance')=='injected_synthetic_held_out_sessions' else None
 def reset(self):
  with self.transaction() as c:
   c.execute('DELETE FROM reports');c.execute('DELETE FROM anomaly_events');c.execute('DELETE FROM evaluations')
storage=Storage()
