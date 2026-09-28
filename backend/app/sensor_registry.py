from __future__ import annotations

import math


SENSOR_DEFINITIONS={
    "bmp280":{"label":"BMP280 temperature / pressure","expected":["temperature_c","pressure_hpa"]},
    "humidity":{"label":"External humidity sensor","expected":["humidity_pct"]},
    "mpu6050":{"label":"MPU6050 vibration / tilt","expected":["accel_x_ms2","accel_y_ms2","accel_z_ms2","gyro_x_rads","gyro_y_rads","gyro_z_rads"]},
    "ina219":{"label":"INA219 supply monitor","expected":["bus_voltage_v","current_ma","power_mw"]},
    "rain":{"label":"Tipping-bucket rain gauge","expected":["rain_rate_mm_h","rain_total_mm"]},
    "wind":{"label":"Cup anemometer","expected":["wind_speed_ms"]},
    "vane":{"label":"Wind vane","expected":["wind_direction_deg"]},
    "solar":{"label":"Pyranometer","expected":["solar_wm2"]},
}


def flatten_sensor_values(packet: dict):
    values={};active=[]
    for key,definition in SENSOR_DEFINITIONS.items():
        sensor=packet.get("sensors",{}).get(key,{})
        if not sensor.get("attached"):
            continue
        active.append(key)
        if not sensor.get("valid"):
            continue
        for name,value in sensor.get("values",{}).items():
            if isinstance(value,(int,float)) and math.isfinite(float(value)):
                values[name]=float(value)
    bmp=packet.get("sensors",{}).get("bmp280",{})
    hum=packet.get("sensors",{}).get("humidity",{})
    if bmp.get("attached") and bmp.get("valid"):
        values.update({k:float(v) for k,v in bmp.get("values",{}).items()
                       if k in ("temperature_c","pressure_hpa") and isinstance(v,(int,float))})
    if hum.get("attached") and hum.get("valid"):
        value=hum.get("values",{}).get("humidity_pct")
        if isinstance(value,(int,float)):values["humidity_pct"]=float(value)

    mpu=packet.get("sensors",{}).get("mpu6050",{})
    if mpu.get("attached") and mpu.get("valid"):
        mv=mpu.get("values",{})
        try:
            values["accel_norm_ms2"]=(sum(float(mv[k])**2 for k in ("accel_x_ms2","accel_y_ms2","accel_z_ms2")))**.5
            values["gyro_norm_rads"]=(sum(float(mv[k])**2 for k in ("gyro_x_rads","gyro_y_rads","gyro_z_rads")))**.5
        except (KeyError,TypeError,ValueError):pass
    return values,active


def hardware_status(packet: dict):
    output=[]
    sensors=packet.get("sensors",{})
    for key,definition in SENSOR_DEFINITIONS.items():
        sensor=sensors.get(key,{"attached":False,"valid":False,"sensor_type":"Not configured","values":{}})
        attached=bool(sensor.get("attached"))
        valid=bool(sensor.get("valid")) if attached else False
        output.append({
            "key":key,"label":definition["label"],"attached":attached,"valid":valid,
            "status":"Healthy" if attached and valid else "Detected, invalid" if attached else "Not attached",
            "sensor_type":sensor.get("sensor_type","Unknown"),"values":sensor.get("values",{}),
            "processed_by_ml":attached and valid,
        })
    return output
