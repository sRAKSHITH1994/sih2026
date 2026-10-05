"""One-minute TP/TPH training; threshold selected independently of test results."""
import sys,json,argparse,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.lstm_autoencoder import NumpyLSTMAutoencoder
from app.config import CORE_FEATURES,CORE_TP_FEATURES,MODEL_TP_PATH,MODEL_TPH_PATH


def windows(path,features,normal_only=True,stride=1):
    frame=pd.read_csv(path);cols={'temperature_c':'temperature','pressure_hpa':'pressure','humidity_pct':'humidity'}
    # Explicit ns conversion is stable for both pandas 2.x and 3.x datetime units.
    times=pd.to_datetime(frame.timestamp,utc=True).values.astype('datetime64[ns]').astype('int64')/1e9
    values=frame[[cols[k] for k in features]].to_numpy(np.float32)
    labels=frame.anomaly.to_numpy() if 'anomaly' in frame else np.zeros(len(frame))
    seq=[];ys=[]
    for i in range(0,len(frame)-19,stride):
        sl=slice(i,i+20)
        if any(frame[k].iloc[sl].nunique()!=1 for k in ['station_id','session_id'] if k in frame):continue
        if not np.all(np.diff(times[sl])==60) or not np.isfinite(values[sl]).all():continue
        if normal_only and np.any(labels[sl]!=0):continue
        seq.append(values[sl]);ys.append(bool(np.any(labels[sl]!=0)))
    return np.asarray(seq,dtype=np.float32).reshape(-1,20,len(features)),np.asarray(ys,dtype=bool)


def score(truth,losses,threshold):
    pred=losses>threshold;tp=int((pred&truth).sum());tn=int((~pred&~truth).sum());fp=int((pred&~truth).sum());fn=int((~pred&truth).sum())
    recall=tp/max(1,tp+fn);specificity=tn/max(1,tn+fp)
    return {'accuracy':(tp+tn)/max(1,len(truth)),'balanced_accuracy':(recall+specificity)/2,
      'recall':recall,'specificity':specificity,'precision':tp/max(1,tp+fp),'f1':2*tp/max(1,2*tp+fp+fn),
      'confusion':{'tp':tp,'tn':tn,'fp':fp,'fn':fn},'windows':len(truth)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=ROOT/'backend/data')
    parser.add_argument('--threshold-percentile',type=float,default=97.)
    parser.add_argument('--tp-threshold-percentile',type=float);parser.add_argument('--tph-threshold-percentile',type=float)
    parser.add_argument('--sweep',type=float,nargs='+',default=[90,95,97,98,99,99.2,99.5]);parser.add_argument('--epochs',type=int,default=24)
    args=parser.parse_args();spans=[];seen=set()
    for name in ['train','val','test']:
        f=pd.read_csv(args.data_dir/(name+'.csv'));ts=pd.to_datetime(f.timestamp,utc=True)
        if not len(f) or ts.isna().any():raise ValueError('Missing timestamps in '+name)
        spans.append((ts.min(),ts.max()))
        if 'session_id' in f:
            ids=set(f.session_id)
            if seen&ids:raise ValueError('Session leakage across splits')
            seen.update(ids)
    if not spans[0][1]<spans[1][0] or not spans[1][1]<spans[2][0]:raise ValueError('Use disjoint chronological time ranges')
    report={'cadence_seconds':60,'window_length':20,'window_stride_rows':1,'pandas_version':pd.__version__,
      'data_provenance':'Original supplied CSVs; acquisition provenance unverified. Not field certification.',
      'split':'Chronological train/validation/test. No window crosses a gap, session boundary or removed anomaly.',
      'threshold_selection':'CLI percentile of NORMAL validation loss, fixed before viewing test table; profile overrides allowed.',
      'input_sha256':{n:hashlib.sha256((args.data_dir/(n+'.csv')).read_bytes()).hexdigest() for n in ['train','val','test']},'profiles':{}}
    with threadpool_limits(limits=1):
        for name,features,path,hidden in [('TP',CORE_TP_FEATURES,MODEL_TP_PATH,10),('TPH',CORE_FEATURES,MODEL_TPH_PATH,12)]:
            train,_=windows(args.data_dir/'train.csv',features);val,_=windows(args.data_dir/'val.csv',features)
            vx,vy=windows(args.data_dir/'val.csv',features,False);tx,ty=windows(args.data_dir/'test.csv',features,False)
            if not len(train) or not len(val) or not len(tx):raise ValueError('No continuous windows for '+name)
            m=NumpyLSTMAutoencoder(20,len(features),hidden,42);m.feature_names=list(features);m.sample_interval_seconds=60
            m.fit(train,epochs=args.epochs,batch_size=96,learning_rate=.002,verbose=True)
            normal_loss=m.sequence_losses(val);v_loss=m.sequence_losses(vx);t_loss=m.sequence_losses(tx)
            percentile=getattr(args,name.lower()+'_threshold_percentile') or args.threshold_percentile
            if not 0<percentile<100:raise ValueError('Threshold percentile must be between 0 and 100')
            m.threshold=float(np.percentile(normal_loss,percentile));m.score_scale=max(float(np.median(np.abs(normal_loss-np.median(normal_loss))))*6,m.threshold*.12,1e-5)
            m.training_provenance='Continuous normal training; CLI percentile on independent normal validation; test never used to fit or select.'
            m.save(path)
            sweep=[]
            for q in sorted(set(args.sweep+[percentile])):
                threshold=float(np.percentile(normal_loss,q));sweep.append({'percentile':q,'threshold':threshold,'validation':score(vy,v_loss,threshold),'test':score(ty,t_loss,threshold)})
            report['profiles'][name]={'training_windows':len(train),'validation_windows':len(val),'test_windows':len(tx),
              'threshold_percentile':percentile,'threshold':m.threshold,**score(ty,t_loss,m.threshold),'sweep':sweep,
              'label_convention':'Window positive if any of the 20 original rows is anomalous; overlapping windows are not independent events.'}
            print(name,json.dumps(report['profiles'][name]),flush=True)
    (ROOT/'backend/models/lstm_metrics.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
