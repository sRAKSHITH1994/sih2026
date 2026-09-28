from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SensorChannel(BaseModel):
    attached: bool = False
    valid: bool = False
    sensor_type: str = "UNKNOWN"
    values: dict[str, float | int | None] = Field(default_factory=dict)


class LocalBrainReport(BaseModel):
    anomaly: bool = False
    fault_type: str = "NORMAL"
    severity_score: float = Field(default=0.0, ge=0.0, le=100.0)
    severity_level: str = "NORMAL"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    trust_score: float = Field(default=100.0, ge=0.0, le=100.0)
    explanation: str = "Local checks normal."
    affected_sensors: list[str] = Field(default_factory=list)
    warmup_complete: bool = False
    ewma_score: float = 0.0
    cusum_score: float = 0.0
    sensor_health: dict[str, float] = Field(default_factory=dict)
    sensor_health_state: dict[str, str] = Field(default_factory=dict)
    ml_valid: bool = False
    ml_class: int = 0
    ml_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    ml_class_name: str = "WARMUP"
    ml_top_features: str = ""
    failure_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    station_state: str = "NORMAL"
    station_position: dict[str, Any] = Field(default_factory=dict)
    maintenance_action: str = ""
    pre_failure_warning: bool = False
    alarm_state: str = "GREEN"
    trusted_values: dict[str, Any] = Field(default_factory=dict)
    recovery: dict[str, Any] = Field(default_factory=dict)


class LinkStatus(BaseModel):
    type: str = "WIFI_PRIMARY"
    rssi_dbm: int | None = None
    queue_depth: int = 0
    lora_enabled: bool = False
    lora_available: bool = False


class TelemetryPacket(BaseModel):
    schema_version: str = "1.0"
    station_id: str = Field(min_length=1, max_length=64)
    station_name: str = Field(default="AWS Prototype", max_length=128)
    timestamp: datetime | None = None
    uptime_ms: int = Field(default=0, ge=0)
    sequence: int = Field(default=0, ge=0)
    latitude: float | None = None
    longitude: float | None = None
    firmware_version: str = "unknown"
    source_mode: str = "HARDWARE"
    sensors: dict[str, SensorChannel]
    local_brain: LocalBrainReport = Field(default_factory=LocalBrainReport)
    link: LinkStatus = Field(default_factory=LinkStatus)

    @field_validator("sensors")
    @classmethod
    def require_sensor_map(cls, value: dict[str, SensorChannel]):
        if not value:
            raise ValueError("at least one sensor status is required")
        return value


class EvaluationRequest(BaseModel):
    samples_per_scenario: int = Field(default=100, ge=60, le=400)
    stations: int = Field(default=5, ge=3, le=12)
    seed: int = 42


class SimulationStepRequest(BaseModel):
    scenario: str = "normal"
    reset: bool = False
    mirror_station_id: str | None = None
    include_humidity: bool = True


class GlobalDecision(BaseModel):
    category: str
    specific_type: str
    anomaly: bool
    genuine_weather: bool = False
    sensor_fault: bool = False
    communication_fault: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    severity: str
    explanation: str
    affected_features: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
