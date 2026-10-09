from app.sensor_registry import flatten_sensor_values,hardware_status


def test_not_attached_is_explicit_and_not_processed():
    packet={"sensors":{"bmp280":{"attached":True,"valid":True,"values":{"temperature_c":25,"pressure_hpa":1012}},
                       "humidity":{"attached":True,"valid":True,"values":{"humidity_pct":61}},
                       "rain":{"attached":False,"valid":False,"values":{}}}}
    values,active=flatten_sensor_values(packet)
    assert values["humidity_pct"]==61 and "rain" not in active
    rain=next(x for x in hardware_status(packet) if x["key"]=="rain")
    assert rain["status"]=="Not configured" and rain["processed_by_ml"] is False
