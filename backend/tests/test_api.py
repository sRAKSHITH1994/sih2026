from fastapi.testclient import TestClient
from copy import deepcopy

from app.main import app


def sample_packet():
    empty=lambda name:{"attached":False,"valid":False,"sensor_type":name,"values":{}}
    return {
        "station_id":"TEST_NODE","station_name":"Contract test","uptime_ms":1000,"sequence":1,
        "latitude":13.0,"longitude":80.17,"firmware_version":"test",
        "sensors":{
            "bmp280":{"attached":True,"valid":True,"sensor_type":"BMP280","values":{"temperature_c":28.2,"pressure_hpa":1009.8}},
            "humidity":{"attached":True,"valid":True,"sensor_type":"SHT31","values":{"humidity_pct":67.1}},
            "mpu6050":{"attached":True,"valid":True,"sensor_type":"MPU6050","values":{"accel_x_ms2":0.0,"accel_y_ms2":0.0,"accel_z_ms2":9.81,"gyro_x_rads":0.0,"gyro_y_rads":0.0,"gyro_z_rads":0.0}},
            "ina219":{"attached":True,"valid":True,"sensor_type":"INA219","values":{"bus_voltage_v":5.0,"current_ma":105.0,"power_mw":525.0}},
            "rain":empty("TIPPING_BUCKET"),"wind":empty("ANEMOMETER"),
            "vane":empty("WIND_VANE"),"solar":empty("PYRANOMETER"),
        },
        "local_brain":{"anomaly":False,"fault_type":"NORMAL","severity_score":0,"severity_level":"NORMAL",
                       "confidence":.8,"trust_score":100,"explanation":"Normal.","affected_sensors":[],
                       "warmup_complete":False,"ewma_score":0,"cusum_score":0,
                       "sensor_health":{"bmp280":100,"humidity":100,"mpu6050":100,"ina219":100}},
        "link":{"type":"WIFI","rssi_dbm":-48,"queue_depth":0},
    }


def test_ingest_history_and_presence_contract():
    with TestClient(app) as client:
        headers={"X-Station-Token":"sih26073-demo-token"}
        client.post("/api/v1/reset",headers=headers)
        response=client.post("/api/v1/telemetry",headers=headers,json=sample_packet())
        assert response.status_code==200 and response.json()["ok"] is True
        stations=client.get("/api/v1/stations").json()["stations"]
        assert stations[0]["station_id"]=="TEST_NODE"
        hardware=client.get("/api/v1/stations/TEST_NODE/hardware").json()["sensors"]
        rain=next(sensor for sensor in hardware if sensor["key"]=="rain")
        assert rain["status"]=="Not attached" and rain["processed_by_ml"] is False
        client.post("/api/v1/reset",headers=headers)


def test_token_is_required():
    with TestClient(app) as client:
        assert client.post("/api/v1/telemetry",json=sample_packet()).status_code==401


def test_built_dashboard_is_served():
    with TestClient(app) as client:
        response=client.get("/")
        assert response.status_code==200 and "SIH26073" in response.text


def test_humidity_may_be_not_attached_without_creating_fake_data():
    packet=deepcopy(sample_packet())
    packet["station_id"]="NO_HUMIDITY_NODE"
    packet["sensors"]["humidity"]={"attached":False,"valid":False,"sensor_type":"NOT_CONFIGURED","values":{}}
    with TestClient(app) as client:
        headers={"X-Station-Token":"sih26073-demo-token"}
        client.post("/api/v1/reset",headers=headers)
        result=client.post("/api/v1/telemetry",headers=headers,json=packet).json()
        assert result["decision"]["anomaly"] is False
        hardware=client.get("/api/v1/stations/NO_HUMIDITY_NODE/hardware").json()["sensors"]
        humidity=next(sensor for sensor in hardware if sensor["key"]=="humidity")
        assert humidity["status"]=="Not attached" and humidity["processed_by_ml"] is False
        client.post("/api/v1/reset",headers=headers)


def test_simulator_is_explicitly_labelled_and_optional_humidity_is_absent():
    with TestClient(app) as client:
        response=client.post("/api/v1/simulation/step",json={
            "scenario":"station_power_failure","reset":True,"include_humidity":False,
        })
        assert response.status_code==200
        packet=response.json()["target"]["packet"]
        assert packet["source_mode"]=="SIMULATION"
        assert packet["sensors"]["humidity"]["attached"] is False
        assert packet["sensors"]["rain"]["attached"] is False


def test_health_reports_both_temporal_profiles():
    with TestClient(app) as client:
        health=client.get("/api/v1/health").json()
        assert health["ok"] is True
        assert health["model_profiles"]==["TP","TPH"]


def test_warning_before_station_dies_scenario_reaches_prefailure_state():
    with TestClient(app) as client:
        result=None
        for index in range(33):
            result=client.post("/api/v1/simulation/step",json={
                "scenario":"station_power_failure","reset":index==0,"include_humidity":False,
            }).json()
        local=result["target"]["packet"]["local_brain"]
        assert local["pre_failure_warning"] is True
        assert local["failure_risk_score"]>=80
        assert local["alarm_state"]=="RED"
