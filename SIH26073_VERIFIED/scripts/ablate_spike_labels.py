"""Label-only ablation: same raw sessions, weighted 64-32 MLP and split seeds.
Baseline deliberately reproduces the ORIGINAL SPIKE tail-label bug for training
only. Validation/test always use correct current-observation labels. No model
from this diagnostic replaces the selected deployment artifact.
"""
from pathlib import Path
import argparse,copy,json,sys,warnings
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import f1_score
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'edge_training'))
from train_edge_mlp import dataset,metrics,model_prob


def run(seed):
    with threadpool_limits(limits=1):
        x,y,groups=dataset('train',48,seed,220);y=y.copy()
        for group in groups:
            if group['events'] and group['events'][0]['class_id']==1:
                y[group['start']+group['onset']-19:group['stop']]=1
        vx,vy,_=dataset('validation',16,seed,220)
        scaler=StandardScaler().fit(x);sx=scaler.transform(x);counts=np.bincount(y,minlength=10);weights=(len(y)/(10*counts[y])).astype(np.float32)
        model=MLPClassifier(hidden_layer_sizes=(64,32),alpha=.001,batch_size=512,learning_rate_init=.001,random_state=seed,max_iter=1,early_stopping=False)
        best=None;best_score=-1.;best_epoch=0
        for epoch in range(1,101):
            with warnings.catch_warnings():warnings.simplefilter('ignore');model.partial_fit(sx,y,classes=np.arange(10),sample_weight=weights)
            if epoch%5==0:
                score=f1_score(vy,model_prob(model,scaler,vx).argmax(1),average='macro')
                if score>best_score+1e-4:best=copy.deepcopy(model);best_score=score;best_epoch=epoch
                if epoch-best_epoch>=20:break
        tx,ty,_=dataset('test',32,seed+100,220)
        result={'seed':seed,'selected_epoch':best_epoch,'validation_macro_f1':float(best_score),'test':metrics(ty,model_prob(best,scaler,tx).argmax(1))}
        print(seed,result['test']['accuracy'],flush=True);return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--jobs',type=int,default=1);args=p.parse_args()
    if args.jobs>1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:rows=list(pool.map(run,range(5)))
    else:rows=[run(i) for i in range(5)]
    corrected=json.loads((ROOT/'edge_training/artifacts/edge_mlp_metrics.json').read_text())['tests']['large_weighted']
    report={'synthetic':True,'field_accuracy':None,'description':__doc__,'buggy_label_training':rows,'corrected_label_training':corrected,
      'effect':{key:{'buggy_mean':float(np.mean([r['test'][key] for r in rows])),
                     'corrected_mean':float(np.mean([r[key] for r in corrected]))} for key in ['accuracy','balanced_accuracy','macro_f1','binary_accuracy']},
      'per_class_recall':{name:{'buggy_mean':float(np.mean([r['test']['classification'][name]['recall'] for r in rows])),
                                'corrected_mean':float(np.mean([r['classification'][name]['recall'] for r in corrected]))}
                          for name in corrected[0]['classification'] if isinstance(corrected[0]['classification'][name],dict) and 'recall' in corrected[0]['classification'][name] and name not in ['macro avg','weighted avg']}}
    (ROOT/'edge_training/artifacts/label_ablation_metrics.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['effect'],indent=2))
