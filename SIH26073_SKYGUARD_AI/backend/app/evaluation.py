"""Independent held-out raw sessions; labels are used ONLY after inference.

Pipeline binary truth means equipment/sensor fault; a genuine weather event is
normal weather, not a fault. Actual exported MLP and compiled firmware rules are
used. Stateful ESP32 health/recovery/pose and radio/HTTP are not emulated.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import time,hashlib
import numpy as np
from .global_brain import GlobalBrainEngine
from .local_reference import LocalReference,CLASS_NAMES
from .simulator import packet_from_row
from corpus import session,session_seed
from train_edge_mlp import metrics,event_metrics


def binary(truth,pred):
    y=np.asarray(truth,dtype=bool);p=np.asarray(pred,dtype=bool)
    tp=int((y&p).sum());tn=int((~y&~p).sum());fp=int((~y&p).sum());fn=int((y&~p).sum())
    recall=tp/max(1,tp+fn);specificity=tn/max(1,tn+fp)
    return {'tp':tp,'tn':tn,'fp':fp,'fn':fn,'accuracy':float((y==p).mean()),'precision':tp/max(1,tp+fp),
      'recall':recall,'specificity':specificity,'false_alarm_rate':fp/max(1,fp+tn),'f1':2*tp/max(1,2*tp+fp+fn),'balanced_accuracy':(recall+specificity)/2}


def run_injected_evaluation(model_path=None,samples_per_scenario=220,stations=3,seed=42,sessions_per_class=1,require_native=True):
    start=time.perf_counter();n=max(160,min(400,samples_per_scenario));stations=max(3,min(12,stations))
    truth=[];pred=[];local_pred=[];edge_y=[];edge_pred=[];latency=[];global_latency=[];groups=[];scenarios=[]
    explained=alerts=ready=0;origin=datetime(2025,1,1,tzinfo=timezone.utc)
    engine=GlobalBrainEngine();native_used=True
    labels_list=[*CLASS_NAMES,'DATA_LOSS','GENUINE_WEATHER','STATION_POWER_FAILURE']
    all_event_rows={}
    for scenario_index,scenario in enumerate(labels_list):
        sy=[];sp=[];scenario_delays=[];scenario_events=0;scenario_hits=0;typed_hits=0;weather_confirmations=0
        cls=CLASS_NAMES.index(scenario) if scenario in CLASS_NAMES else 0
        for repetition in range(sessions_per_class):
            engine.reset();refs=[LocalReference(require_native=require_native) for _ in range(stations)]
            native_used=native_used and all(r.native is not None for r in refs)
            frame,labels,meta=session(cls,session_seed('evaluation',seed,scenario_index,repetition),n)
            rows=frame.to_dict('records');events=list(meta['events'])
            if scenario=='DATA_LOSS':
                labels[meta['onset']:meta['end']]=1;events=[{'start':meta['onset'],'end':meta['end'],'class_id':-1}]
                for row in rows[meta['onset']:meta['end']]:row.update(bmp_valid=0,temperature_c=None,pressure_hpa=None)
            if scenario=='STATION_POWER_FAILURE':
                labels[meta['onset']:meta['end']]=1;events=[{'start':meta['onset'],'end':meta['end'],'class_id':-1}]
                for i in range(meta['onset'],meta['end']):
                    rows[i]['bus_voltage_v']=max(2.,5.-.035*(i-meta['onset']));rows[i]['current_ma']+=1.8*(i-meta['onset']);rows[i]['power_mw']=rows[i]['bus_voltage_v']*rows[i]['current_ma']
            neighbors=[]
            for j in range(1,stations):
                raw,_,_=session(0,session_seed('evaluation',seed+100+j,scenario_index,repetition),n,weather_front=False)
                neighbors.append(raw.to_dict('records'))
            session_pred=[];session_types=[]
            for i,row in enumerate(rows):
                for j in list(range(1,stations))+[0]:
                    r=dict(row if j==0 or scenario=='GENUINE_WEATHER' else neighbors[j-1][i])
                    if scenario=='GENUINE_WEATHER':
                        progress=min(1.,max(0.,(i-meta['onset'])/45))
                        r['temperature_c']+=5*progress+.01*j;r['pressure_hpa']-=6*progress+.02*j
                        if r['humidity_valid']:r['humidity_pct']+=min(8*progress,100-r['humidity_pct'])
                    when=origin+timedelta(seconds=i)
                    # Identity is opaque and independent of the class name. No labels enter p.
                    boot=hashlib.sha256(f'{seed}/{scenario_index}/{repetition}'.encode()).hexdigest()[:24]
                    p=packet_from_row(r,'EVAL_'+str(j),i,boot,when,j)
                    begin=time.perf_counter();local=refs[j].evaluate(p);p['local_brain']=local
                    d,ms=engine.process(p,when);latency.append((time.perf_counter()-begin)*1000);global_latency.append(ms)
                    if j:continue
                    y=bool(labels[i]);z=bool(d['anomaly'] and not d['genuine_weather'])
                    sy.append(y);sp.append(z);truth.append(y);pred.append(z);local_pred.append(bool(local['anomaly']))
                    session_pred.append(z);session_types.append(d['specific_type']);ready+=bool(d['evidence']['lstm']['ready'])
                    weather_confirmations+=bool(d['genuine_weather'])
                    if scenario in CLASS_NAMES and local['ml_valid']:
                        edge_y.append(int(labels[i]));edge_pred.append(local['ml_class'])
                    if z:
                        alerts+=1
                        evidence=d['evidence'];supported=bool(local.get('ml_valid') and local.get('ml_top_features')) or bool(local.get('affected_sensors')) or bool(evidence['lstm'].get('shapley')) or bool(evidence['multivariate']['invalid_features'])
                        explained+=bool(d.get('explanation') and supported)
            for event in events:
                scenario_events+=1;a,b=event['start'],event['end'];hits=np.flatnonzero(session_pred[a:b])
                typed_hits+=int(scenario in session_types[a:b])
                if len(hits):scenario_hits+=1;scenario_delays.append(int(hits[0]))
        row={'scenario':scenario.lower(),'samples':len(sy),'confusion':binary(sy,sp),'events':scenario_events,'events_detected':scenario_hits,
             'event_detection_rate':scenario_hits/scenario_events if scenario_events else None,
             'typed_events_detected':typed_hits,'delay_seconds':scenario_delays,
             'detection_latency_samples':float(np.median(scenario_delays)) if scenario_delays else None,
             'p95_delay_seconds':float(np.percentile(scenario_delays,95)) if scenario_delays else None,
             'detected':scenario_hits==scenario_events if scenario_events else not any(sp),
             'weather_confirmation_samples':weather_confirmations}
        scenarios.append(row)
    elapsed=time.perf_counter()-start;bm=binary(truth,pred);event_count=sum(r['events'] for r in scenarios);caught=sum(r['events_detected'] for r in scenarios)
    mean=float(np.mean(latency));p95=float(np.percentile(latency,95));global_mean=float(np.mean(global_latency))
    result={'created_at':datetime.now(timezone.utc).isoformat(),'provenance':'injected_synthetic_held_out_sessions','synthetic':True,'field_accuracy':None,
      'seed':seed,'sessions_per_class':sessions_per_class,'samples_per_scenario':n,'requested_samples_per_scenario':samples_per_scenario,'stations':stations,'samples':len(truth),
      'scope':('Host raw feature extraction + exported float32 MLP + '+('actual compiled firmware rules' if native_used else 'Python portable rule reference, verified against compiled firmware in the native test suite')+' + Global Brain. Physical health/recovery/pose, networking, storage, dashboard excluded. LSTM not ready in these short sessions; evaluated separately.'),
      'native_rules_used':native_used,'labels_reach_inference':False,'binary_metrics':bm,'confusion':{k:bm[k] for k in ['tp','tn','fp','fn']},
      'edge_ten_class':metrics(np.array(edge_y),np.array(edge_pred)),'local_binary_metrics':binary(truth,local_pred),'scenarios':scenarios,
      'event_detection':{'events':event_count,'detected':caught,'rate':caught/event_count if event_count else None,
          'definition':'At least one fault alert DURING each injected event; no post-event allowance. This can include a wrong fault type. See typed_events_detected.'},
      'explanation_coverage':explained/alerts if alerts else None,'explained_alert_samples':explained,'alert_samples':alerts,'lstm_ready_target_samples':ready,
      'latency':{'mean_inference_ms':mean,'p95_inference_ms':p95,'mean_global_inference_ms':global_mean,
        'p95_global_inference_ms':float(np.percentile(global_latency,95)),'throughput_per_second':len(latency)/elapsed,
        'total_packets_all_stations':len(latency),'elapsed_seconds':elapsed,'scope':'Measured synchronous host compute. Excludes network, SQLite, radio, ESP32 and browser.'},
      'warning':'Synthetic raw-input benchmark; genuine weather is not a sensor fault. No field accuracy or calibrated failure prediction. Ten-class MLP test numbers are separate from rule/server fusion.',
      'criteria':[{'name':'Detection Accuracy','value':f"{100*bm['balanced_accuracy']:.2f}% binary balanced accuracy on injected sessions"},
        {'name':'Real-Time Capability','value':f'{p95:.3f} ms host p95; excludes transport'},
        {'name':'Explainability','value':f'{explained}/{alerts} alerts with measured supporting evidence'}]}
    return result
