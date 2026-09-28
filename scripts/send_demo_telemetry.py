from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
import urllib.request


def packet(station_id):
    return {
        "schema_version":"1.0","station_id":station_id,"station_name":"Tec Titans Prototype",
        "timestamp":datetime.now(timezone.utc).isoformat(),"uptime_ms":1000,"sequence":1,
        "latitude":13.0033,"longitude":80.1710,"firmware_version":"demo-packet",
        "source_mode":"SIMULATION",
        "sensors":{
            "bmp280":{"attached":True,"valid":True,"sensor_type":"BMP280","values":{"temperature_c":29.4,"pressure_hpa":1008.2}},
            "humidity":{"attached":False,"valid":False,"sensor_type":"NOT_CONFIGURED","values":{}},
            "mpu6050":{"attached":True,"valid":True,"sensor_type":"MPU6050","values":{"accel_x_ms2":.02,"accel_y_ms2":.01,"accel_z_ms2":9.81,"gyro_x_rads":.001,"gyro_y_rads":.002,"gyro_z_rads":.001}},
            "ina219":{"attached":True,"valid":True,"sensor_type":"INA219","values":{"bus_voltage_v":5.03,"current_ma":108.0,"power_mw":543.0}},
            "rain":{"attached":False,"valid":False,"sensor_type":"Not attached","values":{}},
            "wind":{"attached":False,"valid":False,"sensor_type":"Not attached","values":{}},
            "vane":{"attached":False,"valid":False,"sensor_type":"Not attached","values":{}},
            "solar":{"attached":False,"valid":False,"sensor_type":"Not attached","values":{}},
        },
        "local_brain":{"anomaly":False,"fault_type":"NORMAL","severity_score":0,"severity_level":"NORMAL",
                       "confidence":.97,"trust_score":100,"explanation":"All configured local sensors are normal.",
                       "affected_sensors":[],"warmup_complete":False,"ewma_score":0,"cusum_score":0},
        "link":{"type":"WIFI","rssi_dbm":-51,"queue_depth":0},
    }


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--url",default="http://127.0.0.1:8000/api/v1/telemetry")
    parser.add_argument("--token",default="sih26073-demo-token");parser.add_argument("--station",default="DEMO_AWS_01")
    args=parser.parse_args();body=json.dumps(packet(args.station)).encode()
    request=urllib.request.Request(args.url,data=body,method="POST",
        headers={"Content-Type":"application/json","X-Station-Token":args.token})
    with urllib.request.urlopen(request,timeout=5) as response:
        print(response.read().decode())


if __name__=="__main__":main()
