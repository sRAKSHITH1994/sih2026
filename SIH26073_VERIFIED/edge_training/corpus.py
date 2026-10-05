"""Independent 1 Hz synthetic sessions; labels never enter detector inputs.

Persistent faults are labelled [onset, end); recovery is NORMAL immediately.
SPIKE labels only the 1–2 altered observations, never the return transition.
RAIN_BLOCKED is an injected failure, not proof that high humidity implies rain.
Normal wet-without-rain/calm/steady-vane controls intentionally overlap faults.
"""
import numpy as np
import pandas as pd
from feature_pipeline import CLASS_NAMES

PROFILES = ('core', 'core_humidity', 'wind', 'rain', 'full')
SENSORS = ('bmp', 'humidity', 'mpu', 'ina', 'rain', 'wind', 'vane', 'solar')
COLUMNS = {'bmp': ['temperature_c', 'pressure_hpa'], 'humidity': ['humidity_pct'],
 'mpu': ['ax','ay','az','gx','gy','gz'], 'ina': ['bus_voltage_v','current_ma','power_mw'],
 'rain': ['rain_rate_mm_h'], 'wind': ['wind_speed_ms'], 'vane': ['wind_direction_deg'], 'solar': ['solar_wm2']}


def session(class_id, seed, length=220, profile=None, weather_front=None):
    rng = np.random.default_rng(seed)
    eligible = ('rain','full') if class_id == 7 else ('wind','full') if class_id in (8,9) else PROFILES
    profile = profile or eligible[int(rng.integers(len(eligible)))]
    if profile not in eligible:
        raise ValueError('Fault requires a sensor absent from this profile')
    k = np.arange(length); onset = int(rng.integers(40,65)); end = length-int(rng.integers(35,55))
    phase = rng.uniform(0,2*np.pi); hour = rng.uniform(0,24)
    day = np.sin(2*np.pi*(hour*3600+k)/86400)
    front = bool(rng.random()<.35) if weather_front is None else weather_front
    front_curve = (np.tanh((k-rng.uniform(60,160))/rng.uniform(30,90))+1)/2 if front else np.zeros(length)
    t = rng.uniform(14,37)+rng.uniform(2,6)*day+rng.uniform(-4,-1)*front_curve+rng.normal(0,rng.uniform(.025,.09),length)
    p = rng.uniform(960,1025)+.2*np.sin(k/220+phase)-rng.uniform(1,4)*front_curve+rng.normal(0,rng.uniform(.04,.14),length)
    h = np.clip(rng.uniform(35,90)-3*day+rng.uniform(3,9)*front_curve+rng.normal(0,.25,length),5,100)
    quantized = bool(rng.integers(0,2))
    h = np.round(h) if quantized else np.round(h,2)
    ax=rng.normal(0,.012,length); ay=rng.normal(0,.012,length); az=9.81+rng.normal(0,.025,length)
    gx=rng.normal(0,.003,length); gy=rng.normal(0,.003,length); gz=rng.normal(0,.003,length)
    v=rng.uniform(4.9,5.15)+rng.normal(0,.015,length); c=rng.uniform(70,160)+4*np.sin(k/20)+rng.normal(0,2,length)
    wind=np.maximum(0,rng.uniform(1,6)+.4*np.sin(k/30)+rng.normal(0,.2,length))
    vane=(rng.uniform(0,360)+np.cumsum(rng.normal(0,3,length)))%360
    rainy=rng.random()<.4
    rain=np.where(rng.random(length)<.25,rng.uniform(3,15,length),0) if rainy else np.zeros(length)
    solar=np.maximum(0,650*np.maximum(0,day)+rng.normal(0,6,length))
    # Legitimate calm, stable direction and humid dry periods prevent shortcuts.
    if class_id==0:
        if rng.random()<.25: wind[onset:end]=0
        if rng.random()<.25: vane[onset:end]=np.round(vane[onset]/5)*5
        if rng.random()<.25: h[onset:end]=np.round(rng.uniform(86,99));rain[onset:end]=0
    y=np.zeros(length,dtype=np.int64);events=[]
    if class_id==1:
        for at in range(onset,end,18):
            duration=int(rng.integers(1,3));channel=rng.choice(['t','p','h'] if profile!='core' else ['t','p'])
            array={'t':t,'p':p,'h':h}[channel];array[at:at+duration]+=rng.choice([-1,1])*rng.uniform(6,16)
            y[at:at+duration]=class_id;events.append({'start':at,'end':at+duration,'class_id':class_id})
    elif class_id:
        y[onset:end]=class_id;events.append({'start':onset,'end':end,'class_id':class_id});n=end-onset
        if class_id==2:
            channel=t if rng.random()<.5 else p
            channel[onset:end]+=rng.choice([-1,1])*np.linspace(.02,rng.uniform(6,15),n)
        elif class_id==3:
            t[onset:end]=t[onset-1];p[onset:end]=p[onset-1]
            if rng.random()<.5:h[onset:end]=h[onset-1]
        elif class_id==4:
            t[onset:end]+=rng.normal(0,rng.uniform(.8,2.4),n);p[onset:end]+=rng.normal(0,rng.uniform(1,3.6),n)
        elif class_id==5:
            v[onset:end]=rng.uniform(3.3,4.35)+rng.normal(0,.03,n);c[onset:end]+=rng.uniform(40,140)+rng.normal(0,12,n)
        elif class_id==6:
            az[onset:end]+=rng.normal(0,rng.uniform(1.4,3.2),n);gx[onset:end]+=rng.normal(0,rng.uniform(.5,1.5),n)
        elif class_id==7:
            rain[:onset]=np.where(rng.random(onset)<.4,rng.uniform(3,15,onset),0)
            rain[onset:end]=0;h=np.maximum(h,rng.uniform(85,98));p[onset:end]-=np.linspace(0,1,n)
        elif class_id==8:wind[onset:end]=0
        elif class_id==9:vane[onset:end]=vane[onset-1]
    masks={s:True for s in SENSORS}
    absent={'core':('humidity','rain','wind','vane','solar'),'core_humidity':('rain','wind','vane','solar'),
            'wind':('rain','solar'),'rain':('wind','vane','solar'),'full':()}[profile]
    for s in absent:masks[s]=False
    values=dict(temperature_c=t,pressure_hpa=p,humidity_pct=h,ax=ax,ay=ay,az=az,gx=gx,gy=gy,gz=gz,
      bus_voltage_v=v,current_ma=c,power_mw=v*c,wind_speed_ms=wind,wind_direction_deg=vane,rain_rate_mm_h=rain,solar_wm2=solar)
    for s,names in COLUMNS.items():
        for name in names:
            if not masks[s]:values[name]=np.zeros(length)
    frame=pd.DataFrame(values,dtype=np.float32)
    frame['timestamp_ms']=k*1000
    for s,valid in masks.items():frame[s+'_valid']=float(valid)
    return frame,y,{'onset':onset,'end':end,'events':events,'seed':int(seed),'profile':profile,
                    'humidity_quantized':quantized,'weather_front':front,'synthetic':True}


def session_seed(split,run_seed,class_id,index):
    # Disjoint namespaces for fitting, selection, test, and integrated evaluation.
    base={'train':100_000_000,'validation':200_000_000,'test':300_000_000,'evaluation':400_000_000}[split]
    return base+int(run_seed)*100_000+int(class_id)*1000+int(index)
