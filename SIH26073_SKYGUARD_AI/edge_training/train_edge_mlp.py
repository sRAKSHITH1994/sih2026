"""Ten-class grouped five-seed model comparison, selection and float32 export.

Selection uses validation macro-F1 across seeds. Test folds are scored only after
selection is locked. Seed zero is the predeclared deployment artifact, not the
best test seed. No synthetic result is a field accuracy estimate.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,os,warnings
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import joblib,numpy as np
import pandas as pd
from sklearn.neural_network import MLPClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score,balanced_accuracy_score,f1_score,confusion_matrix,classification_report
from threadpoolctl import threadpool_limits
from feature_pipeline import FEATURE_NAMES,CLASS_NAMES,extract_sequence
from corpus import session,session_seed
from inference import gate,infer

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'edge_training/artifacts'
CANDIDATES=[
 dict(name='small_resample',hidden=(24,12),balance='resample',alpha=.001,patience=20),
 dict(name='large_resample',hidden=(64,32),balance='resample',alpha=.001,patience=20),
 dict(name='large_weighted',hidden=(64,32),balance='weighted',alpha=.001,patience=20),
 dict(name='large_regularized',hidden=(64,32),balance='weighted',alpha=.01,patience=40)]


def real_dataset(path):
    frame=pd.read_csv(path)
    required={'session_id','split','ground_truth','timestamp_ms','bmp_valid','humidity_valid','mpu_valid','ina_valid'}
    if required-set(frame):raise ValueError('Missing columns: '+str(sorted(required-set(frame))))
    if frame[list(required)].isna().any().any():raise ValueError('Independent ground_truth, split and session identity must be supplied for every row.')
    if not set(frame.split).issubset({'train','validation','test'}):raise ValueError('split must be train, validation or test')
    if any(frame.groupby('session_id').split.nunique()>1):raise ValueError('Session leakage: a session appears in multiple splits')
    if not set(frame.ground_truth).issubset(CLASS_NAMES):raise ValueError('ground_truth must be a manually verified MLP class: '+str(CLASS_NAMES))
    result={}
    for split in ['train','validation','test']:
        xx=[];yy=[];groups=[]
        for sid,group in frame[frame.split==split].groupby('session_id',sort=False):
            ts=group.timestamp_ms.to_numpy()
            if len(ts)<20 or np.any(np.diff(ts)<=0):raise ValueError('Each session requires >=20 strictly increasing samples; split reboots into new sessions: '+str(sid))
            # Gaps and invalid BMP readings terminate a segment; never join distant readings.
            cuts=np.r_[0,np.flatnonzero((np.diff(ts)<750)|(np.diff(ts)>1250))+1,len(group)]
            for lo,hi in zip(cuts[:-1],cuts[1:]):
                segment=group.iloc[lo:hi].copy()
                for key in ['rain','wind','vane','solar']:
                    if key+'_valid' not in segment:segment[key+'_valid']=0
                channel_columns={'bmp':['temperature_c','pressure_hpa'],'humidity':['humidity_pct'],'mpu':['ax','ay','az','gx','gy','gz'],'ina':['bus_voltage_v','current_ma','power_mw'],'rain':['rain_rate_mm_h'],'wind':['wind_speed_ms'],'vane':['wind_direction_deg'],'solar':['solar_wm2']}
                for channel,names in channel_columns.items():
                    for name in names:
                        if name not in segment:
                            if segment[channel+'_valid'].any():raise ValueError('Missing valid channel '+name)
                            segment[name]=0.
                        segment.loc[segment[channel+'_valid']==0,name]=0.
                numeric=segment[[name for names in channel_columns.values() for name in names]]
                if not np.isfinite(numeric.to_numpy()).all():raise ValueError('Nonfinite value with valid=1 in session '+str(sid))
                if len(segment)<20:continue
                features=extract_sequence(segment);valid=np.convolve(segment.bmp_valid.to_numpy(),np.ones(20),mode='valid')==20
                ids=np.flatnonzero(valid)+19
                xx.append(features[ids]);yy.append(segment.ground_truth.map(CLASS_NAMES.index).to_numpy()[ids]);groups.extend([str(sid)]*len(ids))
        if not xx or not groups:raise ValueError('No eligible 1 Hz windows in '+split)
        result[split]=(np.concatenate(xx),np.concatenate(yy),groups)
    if set(result['train'][1])!=set(range(len(CLASS_NAMES))):raise ValueError('Training split must include all ten classes. Do not substitute model predictions for labels.')
    return result


def metrics(y,p):
    return {'accuracy':float(accuracy_score(y,p)),'balanced_accuracy':float(balanced_accuracy_score(y,p)),
      'macro_f1':float(f1_score(y,p,labels=np.arange(10),average='macro',zero_division=0)),
      'binary_accuracy':float(accuracy_score(y!=0,p!=0)),
      'classification':classification_report(y,p,labels=np.arange(10),target_names=CLASS_NAMES,output_dict=True,zero_division=0),
      'confusion_matrix':confusion_matrix(y,p,labels=np.arange(10)).tolist(),'rows':len(y)}


def dataset(split,count,seed,length):
    xs=[];ys=[];sessions=[];offset=0
    for cls in range(10):
        for n in range(count):
            raw,y,meta=session(cls,session_seed(split,seed,cls,n),length)
            x=extract_sequence(raw)[19:]; y=y[19:]
            xs.append(x);ys.append(y)
            sessions.append(dict(id=f'{split}/{seed}/{cls}/{n}',start=offset,stop=offset+len(y),**meta))
            offset+=len(y)
    return np.concatenate(xs),np.concatenate(ys),sessions


def model_prob(model,scaler,x):return gate(model.predict_proba(scaler.transform(x)),x)


def train_one(seed,args):
    with threadpool_limits(limits=1):
        tx,ty,tgroups=dataset('train',args.train_sessions_per_class,seed,args.length)
        vx,vy,vgroups=dataset('validation',args.validation_sessions_per_class,seed,args.length)
        folder=OUT/'experiments'/f'seed_{seed}';folder.mkdir(parents=True,exist_ok=True)
        scaler=StandardScaler().fit(tx);x=scaler.transform(tx);v=scaler.transform(vx)
        rng=np.random.default_rng(seed);counts=np.bincount(ty,minlength=10)
        target=min(6000,int(np.median(counts[1:])))
        ids=np.concatenate([rng.choice(np.flatnonzero(ty==c),target,replace=counts[c]<target) for c in range(10)])
        rng.shuffle(ids);weights=(len(ty)/(10*counts[ty])).astype(np.float32)
        summaries={}
        for config in CANDIDATES:
            model=MLPClassifier(hidden_layer_sizes=config['hidden'],alpha=config['alpha'],batch_size=512,
               learning_rate_init=.001,random_state=seed,max_iter=1,early_stopping=False)
            best=None;best_score=-1;best_epoch=0;log=[]
            for epoch in range(1,args.epochs+1):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    if config['balance']=='resample':model.partial_fit(x[ids],ty[ids],classes=np.arange(10))
                    else:model.partial_fit(x,ty,classes=np.arange(10),sample_weight=weights)
                if epoch%5==0 or epoch==args.epochs:
                    score=f1_score(vy,gate(model.predict_proba(v),vx).argmax(axis=1),average='macro')
                    log.append({'epoch':epoch,'validation_macro_f1':float(score)})
                    if score>best_score+1e-4:best=copy.deepcopy(model);best_score=score;best_epoch=epoch
                    if epoch-best_epoch>=config['patience']:break
            summaries[config['name']]={'validation':metrics(vy,model_prob(best,scaler,vx).argmax(1)),
              'selected_epoch':best_epoch,'training_log':log,'config':config}
            joblib.dump((best,scaler),folder/(config['name']+'.joblib'))
            print('seed',seed,config['name'],'validation macro-F1',round(best_score,5),flush=True)
        # A second opinion only; training/validation sessions identical to MLP.
        gb=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,l2_regularization=1.,
             learning_rate=.1,early_stopping=False,random_state=seed)
        gb.fit(tx,ty,sample_weight=weights)
        gp=gate(gb.predict_proba(vx),vx)
        summaries['server_boosting']={'validation':metrics(vy,gp.argmax(1))}
        joblib.dump(gb,folder/'server_boosting.joblib')
        for config in CANDIDATES:
            model,scaler=joblib.load(folder/(config['name']+'.joblib'))
            fused=.5*model_prob(model,scaler,vx)+.5*gp
            summaries[config['name']]['server_blend_validation']=metrics(vy,fused.argmax(1))
        (folder/'validation.json').write_text(json.dumps(summaries,indent=2))
        # Save split manifest, never row-shuffle sessions across boundaries.
        (folder/'split_manifest.json').write_text(json.dumps({'train':tgroups,'validation':vgroups},indent=2))
        return seed,summaries


def arrays(model,scaler):
    result={'mean':scaler.mean_.astype(np.float32),'scale':np.maximum(scaler.scale_,1e-6).astype(np.float32)}
    for i in range(3):result[f'w{i+1}']=model.coefs_[i].astype(np.float32);result[f'b{i+1}']=model.intercepts_[i].astype(np.float32)
    return result


def export(model,scaler):
    a=arrays(model,scaler)
    np.savez_compressed(OUT/'edge_mlp.npz',**a,classes=np.array(CLASS_NAMES),feature_names=np.array(FEATURE_NAMES))
    joblib.dump(model,OUT/'edge_mlp.joblib');joblib.dump(scaler,OUT/'edge_scaler.joblib')
    lines=['#pragma once','// Generated float32 arrays; provenance: edge_mlp_metrics.json.',
           f'#define MODEL_HIDDEN_1 {model.coefs_[0].shape[1]}',f'#define MODEL_HIDDEN_2 {model.coefs_[1].shape[1]}']
    mapping={'mean':'INPUT_MEAN','scale':'INPUT_STD',**{f'w{i}':f'ML_W{i}' for i in (1,2,3)},**{f'b{i}':f'ML_B{i}' for i in (1,2,3)}}
    for key,value in a.items():
        def nums(row):return ','.join(f'{float(v):.9e}f' for v in row)
        body=nums(value) if value.ndim==1 else ',\n'.join('{'+nums(row)+'}' for row in value)
        lines.append('static const float '+mapping[key]+''.join(f'[{n}]' for n in value.shape)+'={'+body+'};')
    (ROOT/'firmware/include/model_weights.h').write_text('\n'.join(lines)+'\n')
    return sum(v.nbytes for v in a.values())


def event_metrics(y,p,groups):
    results={name:dict(events=0,detected=0,typed_detected=0,delays_seconds=[]) for name in CLASS_NAMES[1:]}
    for group in groups:
        pred=p[group['start']:group['stop']]
        for event in group['events']:
            cls=event['class_id'];start=max(0,event['start']-19);end=event['end']-19
            row=results[CLASS_NAMES[cls]];row['events']+=1
            hits=np.flatnonzero(pred[start:end]!=0)
            row['typed_detected']+=int(np.any(pred[start:end]==cls))
            if len(hits):row['detected']+=1;row['delays_seconds'].append(int(hits[0]))
    for row in results.values():
        row['detection_rate']=row['detected']/row['events'] if row['events'] else None
        row['median_delay_seconds']=float(np.median(row['delays_seconds'])) if row['delays_seconds'] else None
        row['p95_delay_seconds']=float(np.percentile(row['delays_seconds'],95)) if row['delays_seconds'] else None
    return results


def summarize(rows):
    return {k:{'mean':float(np.mean([r[k] for r in rows])),'std':float(np.std([r[k] for r in rows],ddof=1)) if len(rows)>1 else 0.}
            for k in ['accuracy','balanced_accuracy','macro_f1','binary_accuracy']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--train-sessions-per-class','--repetitions',type=int,default=48)
    parser.add_argument('--validation-sessions-per-class',type=int,default=16)
    parser.add_argument('--test-sessions-per-class',type=int,default=32)
    parser.add_argument('--seeds',type=int,nargs='+',default=[0,1,2,3,4]);parser.add_argument('--seed',type=int)
    parser.add_argument('--epochs',type=int,default=100);parser.add_argument('--length',type=int,default=220)
    parser.add_argument('--jobs',type=int,default=1)
    parser.add_argument('--finalize-only',action='store_true',help='Reuse existing training/validation checkpoints; never refit on test')
    parser.add_argument('--audit-seed-offset',type=int,default=100)
    args=parser.parse_args()
    if args.seed is not None:args.seeds=list(range(args.seed,args.seed+5))
    if len(args.seeds)<5:raise ValueError('At least five grouped seeds required')
    if args.epochs<5:raise ValueError('At least five epochs required')
    OUT.mkdir(exist_ok=True)
    if args.finalize_only:
        runs={s:json.loads((OUT/'experiments'/f'seed_{s}'/'validation.json').read_text()) for s in args.seeds}
    elif args.jobs>1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures=[pool.submit(train_one,s,args) for s in args.seeds];runs=dict(f.result() for f in futures)
    else:runs=dict(train_one(s,args) for s in args.seeds)
    scores={c['name']:float(np.mean([runs[s][c['name']]['validation']['macro_f1'] for s in args.seeds])) for c in CANDIDATES}
    # Retain candidate changes only if validation improves in >=4/5 runs.
    parents={'large_resample':'small_resample','large_weighted':'small_resample','large_regularized':'large_weighted'}
    eligibility={'small_resample':True};comparisons={}
    for child,parent in parents.items():
        deltas=[runs[s][child]['validation']['macro_f1']-runs[s][parent]['validation']['macro_f1'] for s in args.seeds]
        eligibility[child]=np.mean(deltas)>0 and sum(d>0 for d in deltas)>=len(deltas)*.8
        comparisons[child]={'parent':parent,'validation_deltas':deltas,'kept':bool(eligibility[child])}
    selected=max((k for k in scores if eligibility[k]),key=scores.get)
    # Require improvement on average AND at least four seeds before deploying a server blend.
    differences=[runs[s][selected]['server_blend_validation']['macro_f1']-runs[s][selected]['validation']['macro_f1'] for s in args.seeds]
    keep_blend=float(np.mean(differences))>0 and sum(d>0 for d in differences)>=4
    selection={'candidate':selected,'validation_macro_f1':scores,'server_blend_enabled':keep_blend,
               'server_blend_validation_deltas':differences,'deployment_seed':args.seeds[0],'consistency_comparisons':comparisons,'final_audit_seed_offset':args.audit_seed_offset}
    (OUT/'selection_locked.json').write_text(json.dumps(selection,indent=2))
    tests={c['name']:[] for c in CANDIDATES};tests['original']=[];tests['server_boosting']=[];tests['server_blend']=[]
    with np.load(OUT/'original_edge_mlp.npz') as f:original=dict(f)
    for seed in args.seeds:
        with threadpool_limits(limits=1):
            x,y,groups=dataset('test',args.test_sessions_per_class,seed+args.audit_seed_offset,args.length)
            folder=OUT/'experiments'/f'seed_{seed}'
            manifest=json.loads((folder/'split_manifest.json').read_text());manifest['test']=groups
            (folder/'split_manifest.json').write_text(json.dumps(manifest,indent=2))
            gb=joblib.load(folder/'server_boosting.joblib');gp=gate(gb.predict_proba(x),x)
            for config in CANDIDATES:
                model,scaler=joblib.load(folder/(config['name']+'.joblib'));p=infer(x,arrays(model,scaler))
                row={'seed':seed,**metrics(y,p.argmax(1)),'sequences':len(groups),'events':event_metrics(y,p.argmax(1),groups)}
                tests[config['name']].append(row)
                if config['name']==selected:
                    bp=(p+gp)/2;tests['server_blend'].append({'seed':seed,**metrics(y,bp.argmax(1))})
            tests['server_boosting'].append({'seed':seed,**metrics(y,gp.argmax(1))})
            tests['original'].append({'seed':seed,**metrics(y,infer(x,original).argmax(1))})
    deployment=OUT/'experiments'/f'seed_{args.seeds[0]}'
    model,scaler=joblib.load(deployment/(selected+'.joblib'));size=export(model,scaler)
    joblib.dump(joblib.load(deployment/'server_boosting.joblib'),ROOT/'backend/models/edge_second_opinion.joblib')
    sample_x,sample_y,sample_groups=dataset('test',1,args.seeds[0]+args.audit_seed_offset,args.length)
    sample_frame=pd.DataFrame(sample_x,columns=FEATURE_NAMES);sample_frame['label']=sample_y
    sample_frame['sequence_id']=[g['id'] for g in sample_groups for _ in range(g['stop']-g['start'])]
    sample_frame['sample_index']=np.tile(np.arange(19,args.length),len(sample_groups))
    sample_frame.to_csv(OUT/'edge_training_sample.csv',index=False)
    result={'architecture':[56,*model.hidden_layer_sizes,10],'classes':CLASS_NAMES,'features':FEATURE_NAMES,
      'synthetic_training':True,'field_accuracy':None,'window_size':20,'sample_interval_seconds':1,
      'label_convention':'SPIKE only altered samples; persistent faults [onset,end); recovery NORMAL; no onset exclusion.',
      'selection':selection,'run_arguments':vars(args),'validation':runs,'tests':tests,
      'summary':{name:summarize(rows) for name,rows in tests.items()},'test':tests[selected][0],
      'float32_array_bytes':size,'weight_bias_bytes':size-56*2*4,
      'model_npz_sha256':hashlib.sha256((OUT/'edge_mlp.npz').read_bytes()).hexdigest(),
      'warning':'Synthetic independent sessions only; no field accuracy or failure probability. Optional rain/wind/vane faults have ambiguous normal controls.'}
    (OUT/'edge_mlp_metrics.json').write_text(json.dumps(result,indent=2))
    (ROOT/'backend/models/edge_second_opinion.json').write_text(json.dumps({'enabled':keep_blend,'weight':.5 if keep_blend else 0.,'selection':selection},indent=2))
    print(json.dumps({'selection':selection,'summary':result['summary'],'array_bytes':size},indent=2),flush=True)

if __name__=='__main__':main()
