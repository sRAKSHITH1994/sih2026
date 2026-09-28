from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone
import math


SCENARIOS={
    "normal":"Healthy station variation",
    "spike":"Sudden temperature spike",
    "drift":"Progressive pressure/temperature drift",
    "frozen":"Atmospheric channels become frozen",
    "data_loss":"BMP280 communication loss",
    "electrical":"INA219 voltage sag and current rise",
    "mechanical":"MPU6050 vibration/impact",
    "station_power_failure":"Pre-failure station power warning",
    "genuine_weather":"Corroborated event across three stations",
}


@dataclass
class SimulationState:
    index:int=0
    frozen_values:tuple[float,float,float]|None=None


class StationSimulator:
    def __init__(self):self.state=SimulationState()

    def reset(self):self.state=SimulationState()

    @staticmethod
    def _channel(attached,valid,sensor_type,values):
        return {"attached":bool(attached),"valid":bool(valid),"sensor_type":sensor_type,"values":values if attached else {}}

    def _baseline(self,source,index,include_humidity):
        sensors=(source or {}).get("sensors",{})
        bmp=sensors.get("bmp280",{}).get("values",{});hum=sensors.get("humidity",{}).get("values",{})
        ina=sensors.get("ina219",{}).get("values",{});mpu=sensors.get("mpu6050",{}).get("values",{})
        return {
            "temperature":float(bmp.get("temperature_c",28.0+0.35*math.sin(index/16))),
            "pressure":float(bmp.get("pressure_hpa",1008.0+0.18*math.cos(index/20))),
            "humidity":float(hum.get("humidity_pct",67.0+0.8*math.sin(index/22))) if include_humidity else None,
            "voltage":float(ina.get("bus_voltage_v",5.05)),"current":float(ina.get("current_ma",108.0)),
            "ax":float(mpu.get("accel_x_ms2",0.01)),"ay":float(mpu.get("accel_y_ms2",0.01)),
            "az":float(mpu.get("accel_z_ms2",9.81)),"gx":float(mpu.get("gyro_x_rads",0.002)),
            "gy":float(mpu.get("gyro_y_rads",0.002)),"gz":float(mpu.get("gyro_z_rads",0.002)),
        }

    def _one(self,station_id,offset,scenario,source,include_humidity):
        index=self.state.index;onset=25;base=self._baseline(source,index,include_humidity)
        t=base["temperature"]+offset*.03;p=base["pressure"]-offset*.02;h=None if base["humidity"] is None else base["humidity"]+offset*.05
        voltage=base["voltage"];current=base["current"];ax,ay,az=base["ax"],base["ay"],base["az"];gx,gy,gz=base["gx"],base["gy"],base["gz"]
        fault="NORMAL";severity=0.0;confidence=.94;affected=[];valid=True;failure_risk=max(2.0,index*.05);station_state="NORMAL"
        active=index>=onset
        if scenario=="spike" and index==onset and offset==0:t+=13;fault="SPIKE";severity=86;confidence=.94;affected=["bmp280"]
        elif scenario=="drift" and active and offset==0:
            progress=index-onset;t+=.22*progress;p+=.30*progress;fault="DRIFT";severity=min(88,58+progress);confidence=.88;affected=["bmp280"]
        elif scenario=="frozen" and active and offset==0:
            if self.state.frozen_values is None:self.state.frozen_values=(t,p,h or 0)
            t,p,frozen_h=self.state.frozen_values;h=frozen_h if h is not None else None;fault="FROZEN";severity=76;confidence=.94;affected=["bmp280"]+( ["humidity"] if h is not None else [])
        elif scenario=="data_loss" and active and offset==0:valid=False;fault="DATA_LOSS";severity=92;confidence=.99;affected=["bmp280"]
        elif scenario=="electrical" and active and offset==0:
            progress=index-onset;voltage=max(3.2,5.05-.075*progress);current=108+8*progress;fault="ELECTRICAL";severity=min(96,65+progress);confidence=.93;affected=["ina219"];failure_risk=min(98,45+3*progress);station_state="FAILURE_LIKELY" if failure_risk>=80 else "DEGRADING"
        elif scenario=="station_power_failure" and active and offset==0:
            progress=index-onset;voltage=max(3.0,5.05-.10*progress);current=108+5*progress;fault="STATION_DEGRADATION";severity=min(98,70+progress);confidence=.95;affected=["ina219","station"];failure_risk=min(100,55+4*progress);station_state="FAILURE_LIKELY" if failure_risk>=80 else "DEGRADING"
        elif scenario=="mechanical" and active and offset==0:
            progress=index-onset;az+=2.2*math.sin(progress*1.7);gx+=1.2*math.cos(progress);fault="MECHANICAL";severity=71;confidence=.90;affected=["mpu6050"]
        elif scenario=="genuine_weather" and active:
            progress=min(1.0,(index-onset)/12);t+=6*progress;p-=7*progress
            if h is not None:h+=12*progress
            fault="RAPID_CHANGE";severity=74;confidence=.90;affected=["bmp280"]+( ["humidity"] if h is not None else [])
        anomaly=fault!="NORMAL"
        explanation=(f"Simulation mirrors the Local Brain: {fault}." if anomaly else
                     "Simulated Local Brain validation, EWMA/CUSUM, edge MLP and health checks are normal.")
        empty=lambda name:self._channel(False,False,name,{})
        sensors={
            "bmp280":self._channel(True,valid,"BMP280",{"temperature_c":t,"pressure_hpa":p}),
            "humidity":self._channel(h is not None,h is not None,"SHT31" if h is not None else "NOT_CONFIGURED",{"humidity_pct":h} if h is not None else {}),
            "mpu6050":self._channel(True,True,"MPU6050",{"accel_x_ms2":ax,"accel_y_ms2":ay,"accel_z_ms2":az,"gyro_x_rads":gx,"gyro_y_rads":gy,"gyro_z_rads":gz}),
            "ina219":self._channel(True,True,"INA219",{"bus_voltage_v":voltage,"current_ma":current,"power_mw":voltage*current}),
            "rain":empty("TIPPING_BUCKET"),"wind":empty("ANEMOMETER"),"vane":empty("WIND_VANE"),"solar":empty("PYRANOMETER"),
        }
        local={"anomaly":anomaly,"fault_type":fault,"severity_score":severity,"severity_level":"CRITICAL" if severity>=80 else "HIGH" if severity>=60 else "WARNING" if anomaly else "NORMAL",
               "confidence":confidence,"trust_score":max(5,100-failure_risk*.7-(35 if not valid else 0)),"explanation":explanation,"affected_sensors":affected,
               "warmup_complete":index>=19,"ewma_score":severity*.45 if anomaly else 2,"cusum_score":severity*.60 if anomaly else 3,
               "sensor_health":{"bmp280":35 if not valid else 100,"humidity":100 if h is not None else 0,"mpu6050":72 if fault=="MECHANICAL" else 100,"ina219":max(15,100-failure_risk),"rain":0,"wind":0,"vane":0,"solar":0},
               "sensor_health_state":{"bmp280":"FAULT" if not valid else "HEALTHY","humidity":"HEALTHY" if h is not None else "NOT_ATTACHED","mpu6050":"DEGRADED" if fault=="MECHANICAL" else "HEALTHY","ina219":"DEGRADED" if failure_risk>=55 else "HEALTHY"},
               "ml_valid":index>=19,"ml_class":0 if not anomaly else 5 if fault in {"ELECTRICAL","STATION_DEGRADATION"} else 6 if fault=="MECHANICAL" else 3 if fault=="FROZEN" else 2 if fault=="DRIFT" else 1,
               "ml_probability":confidence if index>=19 else 0,"ml_class_name":fault if anomaly else "NORMAL","ml_top_features":"bus_voltage, bus_voltage_delta, current_std" if "ELECT" in fault or "DEGRAD" in fault else "temperature_residual, pressure_residual, cusum_temperature",
               "failure_risk_score":failure_risk,"station_state":station_state,"maintenance_action":"Inspect station supply and battery before shutdown." if failure_risk>=55 else "No immediate maintenance required.",
               "pre_failure_warning":failure_risk>=55,"alarm_state":"RED" if severity>=75 else "YELLOW" if anomaly else "GREEN"}
        return {"schema_version":"1.1","station_id":station_id,"station_name":"Station Simulator","timestamp":datetime.now(timezone.utc).isoformat(),
                "uptime_ms":index*1000,"sequence":index,"latitude":13.0033+offset*.015,"longitude":80.1710+offset*.012,
                "firmware_version":"SIMULATOR-3.0","source_mode":"SIMULATION","sensors":sensors,"local_brain":local,
                "link":{"type":"SIMULATED_HARDWARE_PACKET","rssi_dbm":-48,"queue_depth":0,"lora_enabled":False,"lora_available":False}}

    def step(self,scenario,source=None,include_humidity=True):
        if scenario not in SCENARIOS:raise ValueError(f"Unknown scenario: {scenario}")
        if scenario=="genuine_weather":packets=[self._one("SIM_NEIGHBOR_01",1,scenario,source,include_humidity),self._one("SIM_NEIGHBOR_02",2,scenario,source,include_humidity),self._one("SIM_AWS_01",0,scenario,source,include_humidity)]
        else:packets=[self._one("SIM_AWS_01",0,scenario,source,include_humidity)]
        self.state.index+=1
        return packets


simulator=StationSimulator()
