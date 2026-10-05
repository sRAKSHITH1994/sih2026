import argparse,json,sys
from pathlib import Path
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'edge_training')]
from app.evaluation import run_injected_evaluation
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--samples-per-scenario','--samples',type=int,default=220)
    p.add_argument('--stations',type=int,default=3);p.add_argument('--seed',type=int,default=42);p.add_argument('--sessions-per-class',type=int,default=16)
    p.add_argument('--output',type=Path,default=ROOT/'backend/models/evaluation_metrics.json');a=p.parse_args()
    with threadpool_limits(limits=1):r=run_injected_evaluation(None,a.samples_per_scenario,a.stations,a.seed,a.sessions_per_class,require_native=True)
    a.output.write_text(json.dumps(r,indent=2));print(json.dumps({k:r[k] for k in ['binary_metrics','event_detection','latency','explanation_coverage']},indent=2))
