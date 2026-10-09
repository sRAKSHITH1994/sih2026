import React, { useCallback, useEffect, useMemo, useState } from 'react'

const API = import.meta.env.VITE_API_URL ? `${import.meta.env.VITE_API_URL}/api/v1` : '/api/v1'
const pages = [
  ['live', 'Live Intelligence'],
  ['evaluation', 'Evaluation Criteria'],
  ['hardware', 'Hardware Integration'],
  ['simulation', 'Station Simulator'],
]

async function jsonFetch(path, options) {
  const response = await fetch(path, options)
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`)
  return response.json()
}

const fmt = (value, digits = 1, fallback = '—') => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : fallback
const title = text => String(text || '').toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())

function Brand() {
  return <div className="brand">
    <span className="brand-mark"><i /><i /><i /></span>
    <span>
      <strong>SKY GUARD AI</strong>
      <small>SUPER TECH TITANS</small>
    </span>
  </div>
}

function StatusPill({ decision, reporting = true }) {
  const kind = !reporting ? 'critical' : decision?.anomaly ? (decision?.genuine_weather ? 'weather' : 'warning') : 'normal'
  return <span className={`pill ${kind}`}><i />{!reporting ? 'NOT REPORTING' : title(decision?.category || 'Waiting')}</span>
}

function Sparkline({ values, color = '#65f5b5', label }) {
  const nums = values.filter(Number.isFinite)
  if (nums.length < 2) return <div className="chart-empty">Waiting for live history…</div>
  const min = Math.min(...nums), max = Math.max(...nums), span = max - min || 1
  const points = nums.map((v, i) => `${(i / (nums.length - 1)) * 100},${39 - ((v - min) / span) * 31}`).join(' ')
  const area = `0,44 ${points} 100,44`
  return <div className="spark" aria-label={label}>
    <svg viewBox="0 0 100 44" preserveAspectRatio="none">
      <defs><linearGradient id={`g-${label}`} x1="0" y1="0" x2="0" y2="1"><stop stopColor={color} stopOpacity=".30"/><stop offset="1" stopColor={color} stopOpacity="0"/></linearGradient></defs>
      <line x1="0" y1="12" x2="100" y2="12"/><line x1="0" y1="28" x2="100" y2="28"/>
      <polygon points={area} fill={`url(#g-${label})`} />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.25" vectorEffect="non-scaling-stroke" />
    </svg>
    <span>{fmt(min, 1)}–{fmt(max, 1)}</span>
  </div>
}

function EmptyState() {
  return <section className="empty-state panel">
    <span className="radar"><i/><i/><i/></span>
    <p className="eyebrow">LISTENING FOR STATION</p>
    <h2>Flash the ESP32-S3 and live telemetry will appear here.</h2>
    <p>The backend is ready. Put your laptop IPv4 address in <code>firmware/include/user_config.h</code>, then keep both devices on the same 2.4 GHz Wi‑Fi.</p>
  </section>
}

function Metric({ label, value, unit, sensor, tone = 'green' }) {
  return <article className={`metric-card ${tone}`}>
    <div className="metric-top"><span>{label}</span><small>{sensor}</small></div>
    <strong>{value}<em>{unit}</em></strong>
    <div className="metric-rule"><i /></div>
  </article>
}

function LivePage({ stations, selectedId, setSelectedId, history, error }) {
  const selected = stations.find(s => s.station_id === selectedId) || stations[0]
  if (!selected) return <EmptyState />
  const packet = selected.packet || {}, sensors = packet.sensors || {}, decision = selected.decision || {}
  const bmp = sensors.bmp280?.values || {}, hum = sensors.humidity?.values || {}, ina = sensors.ina219?.values || {}, mpu = sensors.mpu6050?.values || {}
  const records = history.map(h => h.packet?.sensors || {})
  const spatial = decision.evidence?.spatial || {}, lstm = decision.evidence?.lstm || {}
  return <div className="live-layout">
    <aside className="station-rail panel">
      <div className="section-label"><span>STATION NETWORK</span><b>{stations.length}</b></div>
      {stations.map(station => <button key={station.station_id} className={`station-row ${station.station_id === selected.station_id ? 'active' : ''}`} onClick={() => setSelectedId(station.station_id)}>
        <i className={station.reporting ? station.decision?.anomaly ? 'warn-dot' : 'live-dot' : 'off-dot'} />
        <span><strong>{station.station_name || station.station_id}</strong><small>{station.station_id} · {station.reporting ? `${station.age_seconds}s ago` : 'offline'}</small></span>
      </button>)}
      <div className="rail-note"><span>TRANSPORT</span><strong>Wi‑Fi / HTTP</strong><small>Optional LoRa critical-alert fallback</small></div>
    </aside>

    <div className="live-main">
      {error && <div className="error-bar">{error}</div>}
      <section className="decision-card panel">
        <div>
          <p className="eyebrow">GLOBAL BRAIN DECISION</p>
          <div className="decision-title"><StatusPill decision={decision} reporting={selected.reporting}/><span>{fmt((decision.confidence || 0) * 100, 0)}% confidence</span></div>
          <h1>{decision.anomaly ? title(decision.specific_type) : 'Atmospheric conditions are stable'}</h1>
          <p>{decision.explanation}</p>
        </div>
        <div className="decision-score"><small>INFERENCE</small><strong>{fmt(selected.inference_ms, 2)}</strong><span>ms / report</span></div>
      </section>

      <section className="metric-grid">
        <Metric label="AIR TEMPERATURE" value={fmt(bmp.temperature_c, 1)} unit="°C" sensor="BMP280" />
        <Metric label="BAROMETRIC PRESSURE" value={fmt(bmp.pressure_hpa, 1)} unit="hPa" sensor="BMP280" tone="blue" />
        <Metric label="RELATIVE HUMIDITY" value={fmt(hum.humidity_pct, 1)} unit="%" sensor={sensors.humidity?.sensor_type || 'EXTERNAL'} tone="amber" />
        <Metric label="NODE POWER" value={fmt(ina.power_mw, 0)} unit="mW" sensor="INA219" tone="violet" />
      </section>

      <section className="chart-grid panel">
        <div className="chart-head"><div><p className="eyebrow">LIVE TELEMETRY</p><h3>Environmental signal</h3></div><span>{history.length} reports</span></div>
        <div className="chart-row"><span><i className="key green"/>Temperature</span><Sparkline label="temperature" values={records.map(s => Number(s.bmp280?.values?.temperature_c))}/></div>
        <div className="chart-row"><span><i className="key blue"/>Pressure</span><Sparkline label="pressure" color="#55bdf4" values={records.map(s => Number(s.bmp280?.values?.pressure_hpa))}/></div>
        <div className="chart-row"><span><i className="key amber"/>Humidity</span><Sparkline label="humidity" color="#f1b95b" values={records.map(s => Number(s.humidity?.values?.humidity_pct))}/></div>
      </section>

      <section className="evidence-grid">
        <article className="panel evidence-card"><div className="section-label"><span>LOCAL EDGE MLP + RULES</span><b>{packet.local_brain?.warmup_complete ? 'READY' : 'WARM-UP'}</b></div><strong>{title(packet.local_brain?.fault_type || 'Normal')}</strong><p>{packet.local_brain?.explanation || 'Waiting for edge decision.'}</p><dl><div><dt>ML class</dt><dd>{title(packet.local_brain?.ml_class_name || 'Warmup')}</dd></div><div><dt>ML probability</dt><dd>{fmt((packet.local_brain?.ml_probability || 0)*100, 0)}%</dd></div><div><dt>Top features</dt><dd>{packet.local_brain?.ml_top_features || '—'}</dd></div></dl></article>
        <article className="panel evidence-card"><div className="section-label"><span>GLOBAL {lstm.profile || 'TP/TPH'} LSTM</span><b>{lstm.ready ? 'ACTIVE' : 'WARM-UP'}</b></div><strong>{lstm.anomaly ? 'Sequence anomaly' : 'Normal reconstruction'}</strong><p>{lstm.reason || 'Waiting for a complete 20-sample window.'}</p><dl><div><dt>Loss</dt><dd>{fmt(lstm.loss, 4)}</dd></div><div><dt>Threshold</dt><dd>{fmt(lstm.threshold, 4)}</dd></div><div><dt>XAI</dt><dd>{decision.evidence?.xai?.global_method || 'waiting'}</dd></div></dl></article>
        <article className="panel evidence-card"><div className="section-label"><span>STATION SURVIVAL</span><b>{packet.local_brain?.alarm_state || 'GREEN'}</b></div><strong>{fmt(packet.local_brain?.failure_risk_score,0)}% failure risk</strong><p>{packet.local_brain?.maintenance_action || 'No immediate maintenance action.'}</p><dl><div><dt>State</dt><dd>{title(packet.local_brain?.station_state || 'Normal')}</dd></div><div><dt>Trust</dt><dd>{fmt(packet.local_brain?.trust_score,0)}%</dd></div><div><dt>Pre-warning</dt><dd>{packet.local_brain?.pre_failure_warning ? 'ACTIVE' : 'CLEAR'}</dd></div></dl></article>
        <article className="panel evidence-card"><div className="section-label"><span>SPATIAL VERIFICATION</span><b>{spatial.status || 'WAITING'}</b></div><strong>{spatial.neighbor_count || 0} {packet.source_mode==='SIMULATION' ? 'simulated' : 'real'} neighbours</strong><p>{spatial.explanation || 'Only actually received and source-matched station packets are eligible.'}</p><dl><div><dt>Support</dt><dd>{spatial.supporting_neighbors || 0}</dd></div><div><dt>Radius</dt><dd>100 km</dd></div><div><dt>Freshness</dt><dd>120 s</dd></div></dl></article>
      </section>

      <section className="panel diagnostics"><div><p className="eyebrow">DEVICE DIAGNOSTICS</p><h3>Power, movement & link</h3></div><div className="diag-values"><span><small>BUS VOLTAGE</small>{fmt(ina.bus_voltage_v, 2)} V</span><span><small>CURRENT</small>{fmt(ina.current_ma, 1)} mA</span><span><small>ACCEL Z</small>{fmt(mpu.accel_z_ms2, 2)} m/s²</span><span><small>WI‑FI RSSI</small>{packet.link?.rssi_dbm ?? '—'} dBm</span><span><small>SOURCE</small>{packet.source_mode || 'HARDWARE'}</span></div></section>
    </div>
  </div>
}

const criteriaWeights = [['Innovation & Novelty',25],['Detection Accuracy',20],['Real-Time Capability',15],['Explainability',10],['Scalability',10],['Practical Deployability',10],['Visualization / UI',5],['Energy Efficiency',5]]

function EvaluationPage({ evaluation, setEvaluation }) {
  const [running, setRunning] = useState(false), [error, setError] = useState('')
  async function run() {
    setRunning(true); setError('')
    try { setEvaluation(await jsonFetch(`${API}/evaluation/run`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({samples_per_scenario:100,stations:5,seed:42})})) }
    catch (e) { setError(e.message) } finally { setRunning(false) }
  }
  const m = evaluation?.binary_metrics || {}, latency = evaluation?.latency || {}
  return <div className="page-stack">
    <section className="page-intro panel">
      <div><p className="eyebrow">ANOMALY-INJECTED DATA</p><h1>Evaluation Criteria</h1><p>Reproducible normal, spike, drift, frozen, data-loss and multi-station weather tests. These are synthetic pipeline metrics—not field-accuracy claims. Real-hardware trials remain a separate required validation.</p></div>
      <button className="primary-button" onClick={run} disabled={running}>{running ? 'Running benchmark…' : 'Run injected benchmark'}</button>
    </section>
    {error && <div className="error-bar">{error}</div>}
    <section className="score-grid">
      <article className="score-card panel"><span>BALANCED ACCURACY</span><strong>{evaluation ? fmt(m.balanced_accuracy*100,1) : '—'}<em>%</em></strong><small>Sensitivity + specificity</small></article>
      <article className="score-card panel"><span>F1 SCORE</span><strong>{evaluation ? fmt(m.f1*100,1) : '—'}<em>%</em></strong><small>Precision / recall balance</small></article>
      <article className="score-card panel"><span>P95 INFERENCE</span><strong>{evaluation ? fmt(latency.p95_inference_ms,2) : '—'}<em>ms</em></strong><small>Global decision latency</small></article>
      <article className="score-card panel"><span>THROUGHPUT</span><strong>{evaluation ? fmt(latency.throughput_per_second,0) : '—'}<em>/s</em></strong><small>Reports on this machine</small></article>
    </section>
    <section className="evaluation-layout">
      <article className="panel criteria-panel"><div className="section-label"><span>SIH EVALUATION MAP</span><b>100 POINTS</b></div>{criteriaWeights.map(([name, weight], index) => { const result = evaluation?.criteria?.find(c => c.name === name || c.name.startsWith(name.split(' ')[0])); return <div className="criterion" key={name}><span className="criterion-number">{String(index+1).padStart(2,'0')}</span><div><strong>{name}</strong><small>{result ? String(result.value) : 'Evidence appears after benchmark'}</small></div><b>{weight}</b></div>})}</article>
      <article className="panel confusion-panel"><div className="section-label"><span>CONFUSION MATRIX</span><b>{evaluation?.samples || 0} SAMPLES</b></div><div className="matrix"><span/><b>PREDICT NORMAL</b><b>PREDICT ANOMALY</b><b>ACTUAL NORMAL</b><strong className="tn">{evaluation?.confusion?.tn ?? '—'}<small>TRUE NEGATIVE</small></strong><strong className="fp">{evaluation?.confusion?.fp ?? '—'}<small>FALSE POSITIVE</small></strong><b>ACTUAL ANOMALY</b><strong className="fn">{evaluation?.confusion?.fn ?? '—'}<small>FALSE NEGATIVE</small></strong><strong className="tp">{evaluation?.confusion?.tp ?? '—'}<small>TRUE POSITIVE</small></strong></div><p className="benchmark-note">{evaluation?.warning || 'Run the benchmark to produce traceable results.'}</p></article>
    </section>
    <section className="panel scenario-panel"><div className="section-label"><span>SCENARIO COVERAGE</span><b>CONTROLLED INJECTION</b></div><div className="scenario-grid">{['normal','spike','drift','frozen','data_loss','electrical','mechanical','station_power_failure','genuine_weather'].map(name => { const row=evaluation?.scenarios?.find(s=>s.scenario===name); return <div key={name}><i className={row?.detected ? 'pass' : 'waiting'}>{row?.detected ? '✓' : '·'}</i><span><strong>{title(name)}</strong><small>{row ? (name==='normal' ? 'No false alarm requirement' : `${row.detection_latency_samples ?? '—'} sample latency`) : 'Not evaluated'}</small></span></div>})}</div></section>
  </div>
}

const wiring = [
  ['BMP280','Temperature + pressure','I²C','SDA GPIO 8 · SCL GPIO 9','0x76 / 0x77'],
  ['MPU6050','Movement + tilt','I²C','SDA GPIO 8 · SCL GPIO 9','0x68 / 0x69'],
  ['INA219','Voltage + current','I²C','SDA GPIO 8 · SCL GPIO 9','0x40'],
  ['SHT31','External humidity','I²C','SDA GPIO 8 · SCL GPIO 9','0x44'],
  ['DHT22','Humidity alternative','Digital','DATA GPIO 4','No address'],
  ['Green LED','Normal state','Digital','Anode GPIO 2 via 220 Ω','Cathode → GND'],
  ['Yellow LED','Warning state','Digital','Anode GPIO 3 via 220 Ω','Cathode → GND'],
  ['Red LED','Critical state','Digital','Anode GPIO 11 via 220 Ω','Cathode → GND'],
  ['Active buzzer','Audible alarm','Digital','Signal GPIO 12','Use transistor if required'],
]

function HardwarePage({ hardware, station }) {
  const sensors = hardware?.sensors || Object.entries({bmp280:'BMP280 temperature / pressure',humidity:'External humidity sensor',mpu6050:'MPU6050 vibration / tilt',ina219:'INA219 supply monitor',rain:'Tipping-bucket rain gauge',wind:'Cup anemometer',vane:'Wind vane',solar:'Pyranometer'}).map(([key,label])=>({key,label,attached:false,valid:false,status:'Not attached',processed_by_ml:false}))
  return <div className="page-stack">
    <section className="page-intro panel"><div><p className="eyebrow">ESP32-S3-DEVKITC-1-N8</p><h1>Hardware Integration</h1><p>Shared 3.3 V I²C for BMP280, MPU6050 and INA219; optional external humidity and weather instruments; local three-colour alarm and buzzer.</p></div><div className="connection-badge"><i className={station?.reporting?'live-dot':'off-dot'}/><span><small>STATION LINK</small><strong>{station?.reporting ? `${station.packet?.link?.rssi_dbm ?? '—'} dBm` : 'Waiting for ESP32'}</strong></span></div></section>
    <section className="hardware-grid"><article className="panel wiring-panel"><div className="section-label"><span>WIRING MAP</span><b>3.3 V LOGIC</b></div><div className="wiring-table"><div className="table-head"><span>MODULE</span><span>FUNCTION</span><span>BUS</span><span>ESP32-S3</span><span>ADDRESS</span></div>{wiring.map(row=><div className="table-row" key={row[0]}>{row.map((cell,i)=><span key={i} data-label={wiring[0][i]}><strong>{i===0?cell:''}</strong>{i!==0?cell:''}</span>)}</div>)}</div><div className="power-warning"><b>!</b><p><strong>Use 3.3 V logic.</strong> All grounds must be common. Check your exact breakout’s regulator and pull-ups before applying 5 V.</p></div></article>
      <article className="panel wifi-panel"><div className="section-label"><span>NETWORK SETUP</span><b>WI‑FI PRIMARY</b></div><ol><li><span>01</span><p><strong>Connect laptop + ESP32</strong>Use the same 2.4 GHz Wi‑Fi network.</p></li><li><span>02</span><p><strong>Set credentials</strong>Edit <code>firmware/include/user_config.h</code>.</p></li><li><span>03</span><p><strong>Use laptop IPv4</strong>Set <code>DASHBOARD_HOST</code> to <code>192.168.67.159</code>.</p></li><li><span>04</span><p><strong>Optional LoRa</strong>Enable only after wiring a compatible module and providing a receiving gateway.</p></li></ol><div className="endpoint"><small>TELEMETRY ENDPOINT</small><code>http://192.168.67.159:8000/api/v1/telemetry</code></div></article></section>
    <section className="panel presence-panel"><div className="section-label"><span>LIVE SENSOR REGISTRY</span><b>AUTO-INCLUDED IN ML</b></div><div className="sensor-grid">{sensors.map(sensor=><article key={sensor.key} className={sensor.attached ? sensor.valid ? 'healthy' : 'invalid' : 'missing'}><div><i/><span><strong>{sensor.label}</strong><small>{sensor.sensor_type}</small></span></div><b>{sensor.status}</b><p>{sensor.processed_by_ml ? 'Readings included in Global Brain processing' : sensor.attached ? 'Excluded until readings become valid' : 'No sensor attached · no fabricated value'}</p></article>)}</div></section>
    <section className="panel architecture-strip"><div><b>01</b><span><strong>Acquire</strong>BMP + optional humidity + motion + power</span></div><i>→</i><div><b>02</b><span><strong>Local Brain</strong>56 features · MLP · rules · pre-failure</span></div><i>→</i><div><b>03</b><span><strong>Transport</strong>Wi‑Fi queue · optional LoRa alert</span></div><i>→</i><div><b>04</b><span><strong>Global Brain</strong>TP/TPH LSTM · XAI · spatial fusion</span></div></section>
  </div>
}

const simulationScenarios = [
  ['normal','Healthy station variation'],['spike','Sudden temperature spike'],['drift','Progressive atmospheric drift'],
  ['frozen','Frozen sensor values'],['data_loss','BMP280 communication loss'],['electrical','Voltage sag and current rise'],
  ['mechanical','Vibration / impact fault'],['station_power_failure','Warning before station dies'],['genuine_weather','Three-station weather event'],
]

function SimulationPage({ hardwareStations, onActivity }) {
  const [scenario,setScenario]=useState('normal'), [running,setRunning]=useState(false), [result,setResult]=useState(null)
  const [includeHumidity,setIncludeHumidity]=useState(false), [mirror,setMirror]=useState(''), [error,setError]=useState('')
  const tick=useCallback(async reset => {
    try {
      const response=await jsonFetch(`${API}/simulation/step`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario,reset,include_humidity:includeHumidity,mirror_station_id:mirror||null})})
      setResult(response);setError('');onActivity?.()
    } catch(e){setError(e.message);setRunning(false)}
  },[scenario,includeHumidity,mirror,onActivity])
  useEffect(()=>{if(!running)return;tick(false);const timer=setInterval(()=>tick(false),1000);return()=>clearInterval(timer)},[running,tick])
  const target=result?.target || {}, packet=target.packet || {}, local=packet.local_brain || {}, decision=target.decision || {}, sensors=packet.sensors || {}
  return <div className="page-stack simulation-page">
    <section className="page-intro panel"><div><p className="eyebrow">CONTROLLED DIGITAL TWIN</p><h1>Station Simulator</h1><p>This page sends the exact telemetry schema used by the ESP32. Every record is marked <code>SIMULATION</code> and is isolated from physical-station spatial evidence.</p></div><span className="simulation-banner">SIMULATED DATA — NOT HARDWARE</span></section>
    {error&&<div className="error-bar">{error}</div>}
    <section className="simulation-layout">
      <article className="panel simulation-controls"><div className="section-label"><span>SCENARIO CONTROL</span><b>{running?'RUNNING':'STOPPED'}</b></div>
        <label>Fault / event<select value={scenario} onChange={e=>{setScenario(e.target.value);setRunning(false);setResult(null)}}>{simulationScenarios.map(([key,label])=><option key={key} value={key}>{title(key)} — {label}</option>)}</select></label>
        <label>Mirror live baseline<select value={mirror} onChange={e=>setMirror(e.target.value)}><option value="">Use simulator baseline</option>{hardwareStations.map(s=><option key={s.station_id} value={s.station_id}>{s.station_name||s.station_id}</option>)}</select></label>
        <label className="check-row"><input type="checkbox" checked={includeHumidity} onChange={e=>setIncludeHumidity(e.target.checked)}/>Attach simulated SHT31 humidity</label>
        <div className="button-row"><button className="primary-button" onClick={()=>setRunning(v=>!v)}>{running?'Stop simulation':'Start simulation'}</button><button className="secondary-button" onClick={()=>tick(true)}>Reset + one step</button></div>
        <p className="control-note">Anomalies begin after sample 25 so the 20-sample temporal window can warm up.</p>
      </article>
      <article className="panel station-twin"><div className="section-label"><span>VIRTUAL ESP32-S3</span><b>SAMPLE {result?.simulation_index ?? 0}</b></div>
        <div className={`alarm-orb ${(local.alarm_state||'GREEN').toLowerCase()}`}><i/><strong>{local.alarm_state||'GREEN'}</strong><small>LED / BUZZER STATE</small></div>
        <div className="twin-values"><span><small>TEMPERATURE</small>{fmt(sensors.bmp280?.values?.temperature_c)} °C</span><span><small>PRESSURE</small>{fmt(sensors.bmp280?.values?.pressure_hpa)} hPa</span><span><small>HUMIDITY</small>{fmt(sensors.humidity?.values?.humidity_pct)} %</span><span><small>BUS VOLTAGE</small>{fmt(sensors.ina219?.values?.bus_voltage_v,2)} V</span></div>
      </article>
      <article className="panel simulation-decision"><div className="section-label"><span>FUSED RESULT</span><b>{decision.category||'WAITING'}</b></div><h2>{title(decision.specific_type||'Waiting')}</h2><p>{decision.explanation||'Start the simulator to inspect the same Local + Global Brain path used by hardware.'}</p><div className="simulation-kpis"><span><small>CONFIDENCE</small>{fmt((decision.confidence||0)*100,0)}%</span><span><small>FAILURE RISK</small>{fmt(local.failure_risk_score,0)}%</span><span><small>EDGE MLP</small>{fmt((local.ml_probability||0)*100,0)}%</span><span><small>SOURCE</small>{packet.source_mode||'—'}</span></div><div className="xai-box"><small>EXPLAINABLE REASONING</small><strong>{local.ml_top_features||'Waiting for the 20-sample feature window'}</strong><p>{local.maintenance_action}</p></div></article>
    </section>
  </div>
}

export default function App() {
  const [page, setPage] = useState('live'), [stations, setStations] = useState([]), [selectedId, setSelectedId] = useState('')
  const [history, setHistory] = useState([]), [hardware, setHardware] = useState(null), [evaluation, setEvaluation] = useState(null), [error, setError] = useState('')
  const refresh = useCallback(async () => {
    try {
      const result = await jsonFetch(`${API}/stations`); setStations(result.stations || []); setError('')
      if (!selectedId && result.stations?.length) setSelectedId(result.stations[0].station_id)
    } catch (e) { setError(`Backend unavailable: ${e.message}`) }
  }, [selectedId])
  useEffect(() => { refresh(); const timer=setInterval(refresh,2000); return ()=>clearInterval(timer) }, [refresh])
  useEffect(() => { if (!selectedId) return; Promise.all([jsonFetch(`${API}/stations/${selectedId}/history?limit=120`),jsonFetch(`${API}/stations/${selectedId}/hardware`)]).then(([h,w])=>{setHistory(h.history||[]);setHardware(w)}).catch(()=>{}) }, [selectedId,stations])
  useEffect(() => { jsonFetch(`${API}/evaluation/latest`).then(r=>{if(r.available)setEvaluation(r)}).catch(()=>{}) }, [])
  const selected = useMemo(()=>stations.find(s=>s.station_id===selectedId)||stations[0],[stations,selectedId])
  return <div className="app-shell">
    <header><Brand/><nav>{pages.map(([key,label])=><button key={key} onClick={()=>setPage(key)} className={page===key?'active':''}>{label}</button>)}</nav><div className="system-state"><i className={error?'off-dot':'live-dot'}/><span><small>GLOBAL BRAIN</small><strong>{error?'DISCONNECTED':'OPERATIONAL'}</strong></span></div></header>
    <main>{page==='live'&&<LivePage stations={stations} selectedId={selectedId} setSelectedId={setSelectedId} history={history} error={error}/>} {page==='evaluation'&&<EvaluationPage evaluation={evaluation} setEvaluation={setEvaluation}/>} {page==='hardware'&&<HardwarePage hardware={hardware} station={selected}/>} {page==='simulation'&&<SimulationPage hardwareStations={stations.filter(s=>s.packet?.source_mode!=='SIMULATION')} onActivity={refresh}/>}</main>
    <footer><span>SIH26073 · LOCAL + GLOBAL ATMOSPHERIC INTELLIGENCE</span><span>Wi‑Fi primary · Optional LoRa alerts · <b>v3.0 FINAL</b></span></footer>
  </div>
}
