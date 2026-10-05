from __future__ import annotations
from datetime import datetime,timezone
from typing import Any,Literal
import math
from pydantic import BaseModel,Field,field_validator,model_validator

EXPECTED={
 'bmp280':('temperature_c','pressure_hpa'),'humidity':('humidity_pct',),
 'mpu6050':('accel_x_ms2','accel_y_ms2','accel_z_ms2','gyro_x_rads','gyro_y_rads','gyro_z_rads'),
 'ina219':('bus_voltage_v','current_ma','power_mw'),'rain':('rain_rate_mm_h','rain_total_mm'),
 'wind':('wind_speed_ms',),'vane':('wind_direction_deg',),'solar':('solar_wm2',)}
class SensorChannel(BaseModel):
 configured:bool|None=None
 attached:bool=False
 valid:bool=False
 sensor_type:str='UNKNOWN'
 values:dict[str,float|int|None]=Field(default_factory=dict)
 diagnostic:str=''
 @field_validator('values')
 @classmethod
 def finite(cls,v):return {k:x if x is None or math.isfinite(float(x)) else None for k,x in v.items()}
class LocalBrainReport(BaseModel):
 anomaly:bool=False
 fault_type:str='NORMAL'
 severity_score:float=Field(default=0,ge=0,le=100)
 severity_level:str='NORMAL'
 confidence:float|None=Field(default=None,ge=0,le=1)
 confidence_kind:str='heuristic_evidence'
 confidence_available:bool=False
 health_index:float|None=None
 risk_kind:str='heuristic_not_failure_probability'
 trust_score:float=Field(default=0,ge=0,le=100)
 explanation:str='No local evidence supplied.'
 affected_sensors:list[str]=Field(default_factory=list)
 warmup_complete:bool=False
 ewma_score:float=0
 cusum_score:float=0
 sensor_health:dict[str,float]=Field(default_factory=dict)
 sensor_health_state:dict[str,str]=Field(default_factory=dict)
 feature_vector:list[float]|None=Field(default=None,min_length=56,max_length=56)
 ml_valid:bool=False
 ml_class:int=0
 ml_probability:float|None=Field(default=None,ge=0,le=1)
 ml_class_name:str='WARMUP'
 ml_top_features:str=''
 failure_risk_score:float=Field(default=0,ge=0,le=100)
 station_state:str='UNKNOWN'
 station_position:dict[str,Any]=Field(default_factory=dict)
 maintenance_action:str=''
 pre_failure_warning:bool=False
 alarm_state:str='IDLE'
 trusted_values:dict[str,Any]=Field(default_factory=dict)
 recovery:dict[str,Any]=Field(default_factory=dict)
 implementation:str='firmware'
class LinkStatus(BaseModel):
 type:str='WIFI_PRIMARY'
 rssi_dbm:int|None=None
 queue_depth:int=Field(default=0,ge=0)
 dropped_packets:int=Field(default=0,ge=0)
 persistent_queue:bool=False
 lora_enabled:bool=False
 lora_available:bool=False
class TelemetryPacket(BaseModel):
 schema_version:str='2.0'
 station_id:str=Field(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')
 station_name:str=Field(default='AWS Prototype',max_length=128)
 boot_id:str=Field(default='legacy',max_length=64)
 timestamp:datetime|None=None
 sample_age_ms:int|None=Field(default=None,ge=0)
 time_quality:str='UNSPECIFIED'
 replay:bool=False
 uptime_ms:int=Field(default=0,ge=0)
 sequence:int=Field(default=0,ge=0)
 latitude:float|None=Field(default=None,ge=-90,le=90)
 longitude:float|None=Field(default=None,ge=-180,le=180)
 firmware_version:str='unknown'
 source_mode:Literal['HARDWARE','SIMULATION']='HARDWARE'
 sensors:dict[str,SensorChannel]
 local_brain:LocalBrainReport=Field(default_factory=LocalBrainReport)
 link:LinkStatus=Field(default_factory=LinkStatus)
 diagnostics:dict[str,Any]=Field(default_factory=dict)
 @field_validator('timestamp')
 @classmethod
 def aware(cls,v):return v.replace(tzinfo=timezone.utc) if v and v.tzinfo is None else v
 @model_validator(mode='after')
 def channels(self):
  if not self.sensors:raise ValueError('at least one sensor status is required')
  for key,s in self.sensors.items():
   if s.configured is None:s.configured=s.attached
   if not s.attached:s.valid=False
   if s.valid and (key not in EXPECTED or any(s.values.get(n) is None for n in EXPECTED[key])):
    s.valid=False;s.diagnostic='Missing/nonfinite required channel value'
  return self
class EvaluationRequest(BaseModel):
 samples_per_scenario:int=Field(default=100,ge=60,le=400)
 stations:int=Field(default=5,ge=3,le=12)
 seed:int=42
class SimulationStepRequest(BaseModel):
 scenario:str='normal'
 reset:bool=False
 mirror_station_id:str|None=None
 include_humidity:bool=True
 steps:int=Field(default=1,ge=1,le=60)
class GlobalDecision(BaseModel):
 category:str
 specific_type:str
 anomaly:bool=False
 genuine_weather:bool=False
 sensor_fault:bool=False
 communication_fault:bool=False
 confidence:float|None=Field(default=None,ge=0,le=1)
 confidence_kind:str='not_calibrated'
 severity:str='INFO'
 explanation:str
 affected_features:list[str]=Field(default_factory=list)
 evidence:dict[str,Any]=Field(default_factory=dict)
 readiness:str='WARMING_UP'
