from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime,timezone
from pathlib import Path
import json
import time

from fastapi import FastAPI,Header,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import MODEL_PATH,MODEL_TP_PATH,MODEL_TPH_PATH,PROJECT_ROOT,STALE_SECONDS,STATION_TOKEN
from .evaluation import run_injected_evaluation
from .global_brain import GlobalBrainEngine
from .schemas import EvaluationRequest,SimulationStepRequest,TelemetryPacket
from .sensor_registry import hardware_status
from .simulator import SCENARIOS,simulator
from .storage import storage
from .ws import manager


engine:GlobalBrainEngine|None=None


@asynccontextmanager
async def lifespan(app:FastAPI):
    global engine
    storage.initialize()
    engine=GlobalBrainEngine(MODEL_TPH_PATH,MODEL_TP_PATH)
    yield


app=FastAPI(title="SIH26073 Final Local + Global Brain",version="3.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,
                   allow_methods=["*"],allow_headers=["*"])


def require_token(token:str|None):
    if STATION_TOKEN and token!=STATION_TOKEN:
        raise HTTPException(status_code=401,detail="Invalid station token")


@app.get("/api/v1/health")
def health():
    loaded=sorted(engine.models) if engine else []
    return {"ok":True,"model_loaded":bool(loaded),"model_profiles":loaded,
            "model_paths":{"TP":MODEL_TP_PATH.name,"TPH":MODEL_TPH_PATH.name},
            "server_time":datetime.now(timezone.utc).isoformat()}


async def process_packet(packet:TelemetryPacket):
    if engine is None:raise HTTPException(status_code=503,detail="Global Brain is not initialized")
    body=packet.model_dump(mode="json")
    if body.get("timestamp") is None:body["timestamp"]=datetime.now(timezone.utc).isoformat()
    decision,inference_ms=engine.process(body)
    report_id=storage.insert_report(body,decision,inference_ms)
    message={"type":"telemetry","id":report_id,"packet":body,"decision":decision,
             "inference_ms":round(inference_ms,3),"received_at":datetime.now(timezone.utc).isoformat()}
    await manager.broadcast(message)
    return message


@app.post("/api/v1/telemetry")
async def ingest(packet:TelemetryPacket,x_station_token:str|None=Header(default=None)):
    require_token(x_station_token)
    message=await process_packet(packet)
    return {"ok":True,"report_id":message["id"],"decision":message["decision"],
            "inference_ms":message["inference_ms"]}


@app.get("/api/v1/stations")
def stations():
    now=datetime.now(timezone.utc);items=[]
    for row in storage.latest_by_station():
        received=datetime.fromisoformat(row["received_at"])
        age=max(0,(now-received).total_seconds());packet=row["packet"];decision=row["decision"]
        if age>STALE_SECONDS:
            decision={**decision,"category":"COMMUNICATION_FAULT","specific_type":"NOT_REPORTING",
                      "anomaly":True,"communication_fault":True,"confidence":1.0,"severity":"CRITICAL",
                      "explanation":f"No Wi-Fi telemetry received for {age:.0f} seconds."}
        items.append({"station_id":row["station_id"],"station_name":packet.get("station_name"),
                      "received_at":row["received_at"],"age_seconds":round(age,1),"reporting":age<=STALE_SECONDS,
                      "decision":decision,"packet":packet,"inference_ms":row["inference_ms"]})
    return {"stations":items,"stale_seconds":STALE_SECONDS}


@app.get("/api/v1/stations/{station_id}/history")
def station_history(station_id:str,limit:int=120):
    return {"station_id":station_id,"history":storage.recent(station_id,max(1,min(limit,1000)))}


@app.get("/api/v1/stations/{station_id}/hardware")
def station_hardware(station_id:str):
    rows=storage.recent(station_id,1)
    if not rows:raise HTTPException(status_code=404,detail="Station has not reported")
    packet=rows[-1]["packet"]
    return {"station_id":station_id,"firmware_version":packet.get("firmware_version"),
            "link":packet.get("link",{}),"sensors":hardware_status(packet),
            "last_report":rows[-1]["received_at"]}


@app.get("/api/v1/architecture")
def architecture():
    return {
        "local_brain":["BMP280 + external humidity + MPU6050 + INA219 acquisition",
                       "20-sample window + 56 features + validity masks",
                       "trained 56-24-12-10 MLP + EWMA/CUSUM/rule fusion",
                       "sensor health + pre-failure risk + trusted fallback",
                       "green/yellow/red LEDs + buzzer","Wi-Fi store-and-forward + optional LoRa alerts"],
        "global_brain":["dual trained LSTM autoencoders for T/P and T/P/H",
                        "dynamic adaptive model for every attached optional channel",
                        "source-isolated real/simulated neighbour verification",
                        "multivariate physical consistency + exact Shapley explanation",
                        "weather-vs-fault decision fusion"],
        "transport":{"primary":"Wi-Fi","optional":"LoRa critical-alert fallback via a gateway"},
        "simulation":"Manually started, clearly labelled, and never mixed with hardware spatial evidence.",
        "excluded":["fabricated real-neighbour evidence","automatic simulator on startup"],
    }


@app.get("/api/v1/simulation/scenarios")
def simulation_scenarios():
    return {"scenarios":SCENARIOS,"note":"Simulation records are labelled and isolated from hardware evidence."}


@app.post("/api/v1/simulation/step")
async def simulation_step(request:SimulationStepRequest):
    if request.scenario not in SCENARIOS:
        raise HTTPException(status_code=400,detail=f"Unknown scenario. Choose one of: {', '.join(SCENARIOS)}")
    if request.reset:
        simulator.reset()
        if engine:
            for station_id in ("SIM_AWS_01","SIM_NEIGHBOR_01","SIM_NEIGHBOR_02"):
                engine.reset_station(station_id)
    mirror_packet=None
    if request.mirror_station_id:
        rows=storage.recent(request.mirror_station_id,1)
        if rows:mirror_packet=rows[-1]["packet"]
    packets=simulator.step(request.scenario,mirror_packet,request.include_humidity)
    messages=[]
    for raw in packets:
        messages.append(await process_packet(TelemetryPacket.model_validate(raw)))
    target=next((item for item in reversed(messages) if item["packet"]["station_id"]=="SIM_AWS_01"),messages[-1])
    return {"ok":True,"scenario":request.scenario,"generated_packets":len(messages),
            "simulation_index":simulator.state.index,"target":target}


@app.post("/api/v1/evaluation/run")
def evaluate(request:EvaluationRequest):
    if not MODEL_PATH.exists():raise HTTPException(status_code=503,detail="Train the LSTM model first")
    result=run_injected_evaluation(MODEL_PATH,request.samples_per_scenario,request.stations,request.seed)
    storage.save_evaluation(result)
    return result


@app.get("/api/v1/evaluation/latest")
def latest_evaluation():
    result=storage.latest_evaluation()
    if result is None:
        included=MODEL_PATH.parent/"evaluation_metrics.json"
        if included.exists():return {"available":True,"included_reproducible_run":True,**json.loads(included.read_text(encoding="utf-8"))}
        return {"available":False,"message":"Run the injected-data evaluation first."}
    return {"available":True,**result}


@app.post("/api/v1/reset")
def reset(x_station_token:str|None=Header(default=None)):
    require_token(x_station_token)
    storage.reset()
    if engine:engine.reset()
    return {"ok":True}


@app.websocket("/api/v1/ws")
async def websocket(socket:WebSocket):
    await manager.connect(socket)
    try:
        while True:
            message=await socket.receive_text()
            if message=="ping":await socket.send_text("pong")
    except WebSocketDisconnect:manager.disconnect(socket)
    except Exception:manager.disconnect(socket)


FRONTEND_DIST=PROJECT_ROOT/"frontend"/"dist"
if FRONTEND_DIST.exists():
    assets=FRONTEND_DIST/"assets"
    if assets.exists():app.mount("/assets",StaticFiles(directory=assets),name="assets")

    @app.get("/{path:path}",include_in_schema=False)
    def frontend(path:str):
        candidate=FRONTEND_DIST/path
        if path and candidate.is_file():return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST/"index.html")
else:
    @app.get("/",include_in_schema=False)
    def root():return {"name":"SIH26073 Final Global Brain","docs":"/docs","frontend":"Run npm build in frontend/"}
