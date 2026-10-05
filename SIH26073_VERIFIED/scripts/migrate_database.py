"""Copy an existing SQLite database safely, then backfill historical episodes.
The source is opened read-only and is never replaced. Target must not exist.
"""
import argparse,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.storage import Storage

def migrate(source,target):
 source=Path(source).resolve();target=Path(target).resolve()
 if not source.is_file():raise ValueError('Source database does not exist')
 if target.exists():raise ValueError('Target exists; use a new path to avoid overwriting history')
 target.parent.mkdir(parents=True,exist_ok=True)
 src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(target)
 try:src.backup(dst)
 finally:dst.close();src.close()
 store=Storage(target);store.initialize();c=store._connection()
 result={'reports_preserved':c.execute('SELECT COUNT(*) FROM reports').fetchone()[0],
  'historical_events':c.execute("SELECT COUNT(*) FROM anomaly_events WHERE status='HISTORICAL'").fetchone()[0],
  'source_unchanged':True,'note':'Historical classifications are original recorded decisions; they have not been retroactively verified by the new models.'}
 c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close();return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--target',required=True);a=p.parse_args();print(json.dumps(migrate(a.source,a.target),indent=2))
