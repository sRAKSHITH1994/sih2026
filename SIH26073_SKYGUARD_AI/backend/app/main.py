from __future__ import annotations
import asyncio,csv,io,json,hashlib,threading,hmac,secrets,ipaddress,time
from urllib.parse import urlsplit
from contextlib import asynccontextmanager,suppress
from datetime import datetime,timezone,timedelta
from pathlib import Path
from fastapi import FastAPI,Header,HTTPException,Query,WebSocket,WebSocketDisconnect,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse,Response
from fastapi.staticfiles import StaticFiles
from .config import (
    PROJECT_ROOT, STALE_SECONDS, STATION_TOKEN, MODEL_TP_PATH, MODEL_TPH_PATH,
    DASHBOARD_ORIGINS, ALLOW_PUBLIC_DASHBOARD_WRITES,
)
from .global_brain import GlobalBrainEngine
from .schemas import TelemetryPacket,SimulationStepRequest,EvaluationRequest
from .sensor_registry import hardware_status
from .storage import storage
from .ws import manager
engine=None;ingest_lock=threading.RLock()
def require_token(token):
 if not STATION_TOKEN or token!=STATION_TOKEN:raise HTTPException(401,'Valid X-Station-Token required')
def date(v):return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(timezone.utc) if v else None

def station_items():
 now=datetime.now(timezone.utc);items=[]
 for r in storage.latest_by_station():
  p=r['packet'];sample=date(p.get('timestamp'));received=date(r['received_at']);age=max(0,(now-sample).total_seconds()) if sample else None
  # Simulation has virtual acquisition time, and never represents real-time hardware.
  if p.get('source_mode')=='SIMULATION':age=max(0,(now-received).total_seconds())
  fresh=bool(r['live_eligible']) and age is not None and age<=STALE_SECONDS;d=r['decision']
  if not fresh:d={**d,'category':'COMMUNICATION_FAULT','specific_type':'NOT_REPORTING','anomaly':True,'communication_fault':True,'confidence':0.0,'confidence_available':False,'confidence_kind':'not_calibrated','severity':'CRITICAL','explanation':'No fresh measurement. Displayed values are last known observations.'}
  items.append({'station_id':p['station_id'],'station_name':p.get('station_name'),'source_mode':p.get('source_mode','HARDWARE'),'packet':p,'decision':d,
   'reporting':fresh,'age_seconds':round(age,1) if age is not None else None,'received_at':r['received_at'],'inference_ms':r['inference_ms'],'link_active':(now-received).total_seconds()<=STALE_SECONDS})
 return items
async def offline_watch():
 while True:
  await asyncio.sleep(5)
  for s in station_items():
   if s['source_mode']=='HARDWARE' and not s['reporting']:storage.record_offline(s['packet'])
@asynccontextmanager
async def lifespan(app):
 global engine
 storage.initialize();engine=GlobalBrainEngine()
 # Rebuild only current sessions from recorded acquisition times; no event duplication.
 now=datetime.now(timezone.utc)
 for item in station_items():
  if not item['reporting']:continue
  rows=storage.recent(item['station_id'],1500,item['source_mode'])
  for row in rows:
   p=row['packet'];t=date(p.get('timestamp'))
   if row['live_eligible'] and p.get('boot_id')==item['packet'].get('boot_id') and t and (now-t).total_seconds()<1500:engine.process(p,t)
 task=asyncio.create_task(offline_watch())
 yield
 task.cancel()
 with suppress(asyncio.CancelledError):await task
app=FastAPI(title='SIH26073 Sky Guard AI',version='5.0.0',lifespan=lifespan)

# CORS is only needed when the Render API is called directly. The recommended
# Vercel external rewrite keeps requests same-origin, but this exact allow-list
# is useful for diagnostics and avoids the insecure allow_origins=["*"] pattern.
if DASHBOARD_ORIGINS:
 app.add_middleware(
  CORSMiddleware,
  allow_origins=list(DASHBOARD_ORIGINS),
  allow_credentials=True,
  allow_methods=['GET','POST','OPTIONS'],
  allow_headers=['Content-Type','X-Station-Token'],
 )

DASHBOARD_SECRET=secrets.token_bytes(32)

def loopback_request(request):
 host=urlsplit('//'+request.headers.get('host','')).hostname
 try:local_host=host=='localhost' or ipaddress.ip_address(host).is_loopback
 except ValueError:local_host=False
 try:local_peer=ipaddress.ip_address(request.client.host).is_loopback
 except (ValueError,AttributeError):local_peer=False
 return local_host and local_peer

def require_dashboard_token(request,token):
 if token is not None:return require_token(token)
 origin=(request.headers.get('origin') or '').rstrip('/')

 # Hosted SIH demo mode: permit only the explicitly configured Vercel origin.
 # This applies to dashboard-only simulation/evaluation endpoints; telemetry,
 # reset and anomaly acknowledgement still require X-Station-Token.
 if ALLOW_PUBLIC_DASHBOARD_WRITES and origin and origin in DASHBOARD_ORIGINS:
  return

 # Local dashboard behaviour remains unchanged.
 if origin and origin!=str(request.base_url).rstrip('/'):
  raise HTTPException(403,'Cross-origin write rejected')
 if request.headers.get('sec-fetch-site')=='cross-site':
  raise HTTPException(403,'Cross-site write rejected')
 value=request.cookies.get('sih_dashboard','')
 try:
  expiry,sig=value.split('.',1)
  valid=int(expiry)>=time.time() and hmac.compare_digest(sig,hmac.new(hashlib.sha256(DASHBOARD_SECRET+STATION_TOKEN.encode()).digest(),expiry.encode(),'sha256').hexdigest())
 except (ValueError,TypeError):valid=False
 if not (STATION_TOKEN and loopback_request(request) and valid):
  raise HTTPException(401,'X-Station-Token, trusted hosted dashboard, or local dashboard session required')

def legacy_report(report,stale=False):
 result=json.loads(json.dumps(report));p=result.get('packet',{})
 for sensor in p.get('sensors',{}).values():
  observed=dict(sensor.get('values',{}));sensor['raw_values']=observed
  valid=bool(sensor.get('attached') and sensor.get('valid') and not stale)
  sensor['available']=valid;sensor['availability']={k:valid and v is not None for k,v in observed.items()}
  sensor['observations']={k:v if sensor['availability'][k] else None for k,v in observed.items()}
  sensor['values']={k:v if sensor['availability'][k] else '—' for k,v in observed.items()}
 local=p.get('local_brain',{})
 if stale:
  local.update(ml_valid=False,warmup_complete=False,ml_class_name='STALE',fault_type='STALE',
    explanation='No fresh edge observation; the archived decision is not a current model result.')
 local['confidence']=0.;local['confidence_available']=False;local['confidence_kind']='not_calibrated'
 local['ml_score']=local.get('ml_probability') if local.get('ml_valid') else None
 local['ml_probability']=(local.get('ml_probability') or 0.) if local.get('ml_valid') else 0.;local['ml_probability_available']=bool(local.get('ml_valid'))
 local['health_index']=local.get('health_index',local.get('failure_risk_score'));local['health_index_available']=local['health_index'] is not None and not stale
 local['risk_kind']=local.get('risk_kind','heuristic_not_failure_probability')
 d=result.get('decision',{});d['confidence']=0.;d['confidence_available']=False;d['confidence_kind']='not_calibrated'
 lstm=d.get('evidence',{}).get('lstm',{})
 for key in ['loss','threshold']:
  if key in lstm:lstm[key+'_value']=lstm[key];lstm[key+'_available']=lstm[key] is not None;lstm[key]=lstm[key] if lstm[key] is not None else '—'
 return result

@app.get('/api/v1/health')
def health():return {'ok':engine is not None,'model_loaded':bool(engine and engine.models),'model_profiles':list(engine.models) if engine else [],
 'model_paths':{'TP':MODEL_TP_PATH.name,'TPH':MODEL_TPH_PATH.name},'server_time':datetime.now(timezone.utc).isoformat(),'temporal_cadence_seconds':60,'version':'5.0.0'}

async def process_packet(packet:TelemetryPacket,simulation_clock=False):
 if engine is None:raise HTTPException(503,'Engine not initialized')
 now=datetime.now(timezone.utc);p=packet.model_dump(mode='json');sample=packet.timestamp;reason='accepted'
 if sample is None and packet.sample_age_ms is not None:
  sample=now-timedelta(milliseconds=packet.sample_age_ms);p['time_quality']='MONOTONIC_AGE'
 elif sample is not None:p['time_quality']=p['time_quality'] if p['time_quality']!='UNSPECIFIED' else 'SENDER_TIMESTAMP'
 p['timestamp']=sample.isoformat() if sample else None
 identity=hashlib.sha256(json.dumps([p['source_mode'],p['station_id'],p['boot_id'],p['sequence'],p['timestamp'] if p['boot_id']=='legacy' else None]).encode()).hexdigest()
 with ingest_lock:
  old=storage.find_identity(identity)
  if old:return {'type':'telemetry','id':old['id'],'packet':old['packet'],'decision':old['decision'],'inference_ms':old['inference_ms'],'duplicate':True,'ingest_reason':'duplicate'}
  live=sample is not None and -5<=(now-sample).total_seconds()<=STALE_SECONDS
  if p['boot_id']=='legacy':live=False;reason='identity_unverified'
  if simulation_clock:live=True
  if not live and reason=='accepted':reason='time_unverified' if sample is None else 'historical_or_future_packet'
  prior=storage.latest_session(p['station_id'],p['source_mode'],p['boot_id'])
  if prior and (p['sequence']<=prior['sequence'] or (sample and prior['sample_at'] and sample<=date(prior['sample_at']))):live=False;reason='out_of_order'
  current=storage.latest_live(p['station_id'],p['source_mode'])
  if live and not simulation_clock and current and current['boot_id']!=p['boot_id'] and current['sample_at'] and sample<=date(current['sample_at']):live=False;reason='older_than_current_session'
  if live:decision,ms=engine.process(p,sample)
  else:
   local=p['local_brain'];alert=local.get('anomaly',False)
   decision={'category':'HISTORICAL_ALERT' if alert else 'HISTORICAL_DATA','specific_type':local.get('fault_type','ARCHIVED') if alert else 'ARCHIVED','anomaly':alert,
     'severity':local.get('severity_level','INFO'),'confidence':0.0,'confidence_available':False,'confidence_kind':'not_calibrated','readiness':'EXCLUDED_FROM_LIVE',
     'explanation':f'Archived packet ({reason}); excluded from live inference and spatial evidence. '+local.get('explanation',''),
     'evidence':{'local_brain':local,'time_quality':p['time_quality'],'sample_timestamp':p['timestamp'],'recorded_at':now.isoformat(),'timestamp_is_receipt_time':sample is None}};ms=0.
  report_id=storage.insert_report(p,decision,ms,identity,live,reason,now.isoformat())
 message={'type':'telemetry','id':report_id,'packet':p,'decision':decision,'inference_ms':ms,'received_at':now.isoformat(),'duplicate':False,'ingest_reason':reason}
 await manager.broadcast(message);return message
@app.post('/api/v1/telemetry')
async def ingest(packet:TelemetryPacket,x_station_token:str|None=Header(None)):
 require_token(x_station_token);m=await process_packet(packet);return {'ok':True,'report_id':m['id'],**{k:m[k] for k in ['decision','inference_ms','duplicate','ingest_reason']}}
@app.get('/api/v1/stations')
def stations():return {'stations':[legacy_report(s,stale=not s['reporting']) for s in station_items()],'stale_seconds':STALE_SECONDS}
@app.get('/api/v1/stations/{station_id}/history')
def history(station_id:str,limit:int=120,source_mode:str|None=None):
 rows=storage.recent(station_id,max(1,min(limit,2000)),source_mode)
 return {'station_id':station_id,'history':[legacy_report(r) for r in rows],
         'chart_contract':{'time_field':'packet.timestamp','gap_seconds':20,'rendering_supported_by_frozen_frontend':False}}
@app.get('/api/v1/stations/{station_id}/hardware')
def hardware(station_id:str,source_mode:str|None=None):
 item=next((s for s in station_items() if s['station_id']==station_id and (source_mode is None or s['source_mode']==source_mode)),None)
 if not item:raise HTTPException(404,'Station has not reported')
 p=item['packet'];return {'station_id':station_id,'firmware_version':p.get('firmware_version'),'source_mode':p.get('source_mode'),'fresh':item['reporting'],'last_report':item['received_at'],'age_seconds':item['age_seconds'],
  'sensors':hardware_status(p,item['reporting'],item['decision']),'link':p.get('link',{}),'diagnostics':p.get('diagnostics',{}),'station_position':p.get('local_brain',{}).get('station_position',{}),'recovery':p.get('local_brain',{}).get('recovery',{})}
@app.get('/api/v1/anomalies')
def anomalies(station_id:str|None=None,source_mode:str|None=None,status:str|None=None,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
 return storage.events(station_id,source_mode,status,limit,offset)
@app.get('/api/v1/anomalies/export.csv')
def export_events(station_id:str|None=None,source_mode:str|None=None,status:str|None=None):
 records=storage.events(station_id,source_mode,status,10000,0);buf=io.StringIO();fields=['id','station_id','source_mode','specific_type','category','severity','started_at','last_seen','ended_at','status','sample_count','acknowledged','explanation'];w=csv.DictWriter(buf,fieldnames=fields,extrasaction='ignore');w.writeheader()
 for e in records['events']:
  # Protect spreadsheet consumers against formula cells in externally supplied text.
  w.writerow({k:("'"+str(v) if isinstance(v,str) and (v.lstrip().startswith(('=','+','-','@')) or v.startswith(('\t','\r','\n'))) else v) for k,v in e.items()})
 return Response(buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="anomaly_history.csv"'})
@app.post('/api/v1/anomalies/{event_id}/acknowledge')
def acknowledge(event_id:int,x_station_token:str|None=Header(None)):
 require_token(x_station_token)
 if not storage.acknowledge(event_id):raise HTTPException(404,'Event not found')
 return {'ok':True}
@app.post('/api/v1/simulation/step')
async def simulation_step(request:SimulationStepRequest,http_request:Request,x_station_token:str|None=Header(None)):
 require_dashboard_token(http_request,x_station_token)
 from .simulator import simulator,SCENARIOS
 if request.scenario not in SCENARIOS:raise HTTPException(400,'Unknown scenario')
 if request.reset:
  simulator.reset()
  for ident in ['SIM_AWS_01','SIM_NEIGHBOR_01','SIM_NEIGHBOR_02']:engine.reset_station(ident,'SIMULATION')
 mirror=None
 if request.mirror_station_id:
  row=next((s for s in station_items() if s['station_id']==request.mirror_station_id and s['source_mode']=='HARDWARE' and s['reporting']),None)
  if row:mirror=row['packet']
 messages=[]
 for _ in range(request.steps):
  for raw in simulator.step(request.scenario,mirror,request.include_humidity):messages.append(await process_packet(TelemetryPacket.model_validate(raw),simulation_clock=True))
 target=next(m for m in reversed(messages) if m['packet']['station_id']=='SIM_AWS_01')
 return {'ok':True,'scenario':request.scenario,'generated_packets':len(messages),'simulation_index':simulator.index,'target':legacy_report(target),'virtual_time':True}
@app.post('/api/v1/evaluation/run')
def evaluate(request:EvaluationRequest,http_request:Request,x_station_token:str|None=Header(None)):
 require_dashboard_token(http_request,x_station_token)
 from .evaluation import run_injected_evaluation
 result=run_injected_evaluation(None,request.samples_per_scenario,request.stations,request.seed,require_native=False);storage.save_evaluation(result);return result
@app.get('/api/v1/evaluation/latest')
def evaluation_latest():
 result=storage.latest_evaluation();included=PROJECT_ROOT/'backend/models/evaluation_metrics.json'
 if result is None and included.exists():result=json.loads(included.read_text())
 return {'available':result is not None,**(result or {})}
@app.get('/api/v1/models/metrics')
def model_metrics():
 result={}
 for name,path in [('edge',PROJECT_ROOT/'edge_training/artifacts/edge_mlp_metrics.json'),('lstm',PROJECT_ROOT/'backend/models/lstm_metrics.json')]:
  if path.exists():result[name]=json.loads(path.read_text())
 return result
@app.post('/api/v1/reset')
def reset(x_station_token:str|None=Header(None)):
 require_token(x_station_token)
 with ingest_lock:storage.reset();engine.reset()
 return {'ok':True}
@app.websocket('/api/v1/ws')
async def websocket(socket:WebSocket):
 await manager.connect(socket)
 try:
  while True:
   if await socket.receive_text()=='ping':await socket.send_text('pong')
 except (WebSocketDisconnect,RuntimeError):manager.disconnect(socket)
DIST=PROJECT_ROOT/'frontend/dist'
if (DIST/'assets').exists():app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
@app.get('/',include_in_schema=False)
def frontend(request:Request):
 if not (DIST/'index.html').exists():raise HTTPException(503,'Frontend build missing')
 response=FileResponse(DIST/'index.html')
 if loopback_request(request):
  expiry=int(time.time())+12*3600
  payload=str(expiry);signature=hmac.new(hashlib.sha256(DASHBOARD_SECRET+STATION_TOKEN.encode()).digest(),payload.encode(),'sha256').hexdigest()
  response.set_cookie('sih_dashboard',payload+'.'+signature,httponly=True,samesite='strict',path='/api/v1',max_age=12*3600)
 return response
# Deliberately no request-controlled filesystem fallback.

@app.get("/api/v1/architecture")
def architecture():
    return {
        "local_brain":["BMP280 + external humidity + MPU6050 + INA219 acquisition",
                       "20-sample window + 56 features + validity masks",
                       "trained 56-feature 10-class MLP + EWMA/CUSUM/rule fusion",
                       "heuristic health index + accepted-observation trusted fallback",
                       "green/yellow/red LEDs + buzzer","Wi-Fi store-and-forward + optional LoRa alerts"],
        "global_brain":["dual trained LSTM autoencoders for T/P and T/P/H",
                        "sensor-valid gating for optional edge classes",
                        "source-isolated real/simulated neighbour verification",
                        "multivariate physical consistency + exact Shapley explanation",
                        "weather-vs-fault decision fusion"],
        "transport":{"primary":"Wi-Fi","optional":"LoRa critical-alert fallback via a gateway"},
        "simulation":"Manually started, clearly labelled, and never mixed with hardware spatial evidence.",
        "excluded":["fabricated real-neighbour evidence","automatic simulator on startup"],
    }


@app.get("/api/v1/simulation/scenarios")
def simulation_scenarios():
    from .simulator import SCENARIOS
    return {"scenarios":SCENARIOS,"note":"Simulation records are labelled and isolated from hardware evidence."}

