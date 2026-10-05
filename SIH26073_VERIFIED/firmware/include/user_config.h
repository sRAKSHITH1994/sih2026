#ifndef USER_CONFIG_H
#define USER_CONFIG_H

// Edit this file before flashing the ESP32-S3.
#define STATION_ID "AWS_01"
#define STATION_NAME "Tech Titans Prototype"
#define STATION_LATITUDE 13.0033f
#define STATION_LONGITUDE 80.1710f

// Shared 3.3 V I2C bus: BMP280 + MPU6050 + INA219 + optional SHT31.
#define I2C_SDA_PIN 8
#define I2C_SCL_PIN 9

// Present prototype hardware.
#define ENABLE_BMP280 1
#define ENABLE_MPU6050 0
#define ENABLE_INA219 1

// External humidity is currently not connected. Set to 1 after wiring it.
#define ENABLE_EXTERNAL_HUMIDITY 1
#define HUMIDITY_SHT31 1
#define HUMIDITY_DHT22 2
#define HUMIDITY_DHT11 3
#define HUMIDITY_SENSOR_TYPE HUMIDITY_DHT11
#define DHT_DATA_PIN 4

// Optional instruments. Disabled instruments are reported as "Not attached".
#define ENABLE_RAIN_GAUGE 0
#define ENABLE_ANEMOMETER 0
#define ENABLE_WIND_VANE 0
#define ENABLE_PYRANOMETER 0
#define RAIN_PIN 5
#define ANEMOMETER_PIN 6
#define WIND_VANE_PIN 7
#define PYRANOMETER_PIN 10
#define WIND_VANE_USE_LUT 0  // Set to 1 only after calibrating the resistor-ladder vane.
#define WIND_VANE_ADC_MIN_CAL 20
#define WIND_VANE_ADC_MAX_CAL 4075
#define PYRANOMETER_WM2_PER_COUNT 0.3663f
#define ANEMOMETER_MS_PER_HZ 0.67f
#define RAIN_GAUGE_MM_PER_TIP 0.2794f

// Local alarm outputs. Use a 220–330 ohm resistor with each LED. Use a
// transistor driver for any buzzer that exceeds the GPIO current rating.
#define GREEN_LED_PIN 2
#define YELLOW_LED_PIN 3
#define RED_LED_PIN 11
#define BUZZER_PIN 12

// Wi-Fi is the primary link. Use the laptop IPv4 address, never localhost.
#define WIFI_SSID "OPPO A5 Pro 5G w22p"
#define WIFI_PASSWORD "123456789"
#define DASHBOARD_HOST "10.134.25.155"
#define DASHBOARD_PORT 8000
#define STATION_TOKEN "sih26073-demo-token"

// Optional SX127x LoRa alert fallback. It requires a second LoRa gateway.
#define ENABLE_LORA 0
#define LORA_FREQUENCY_HZ 433000000L
#define LORA_SCK_PIN 18
#define LORA_MISO_PIN 17
#define LORA_MOSI_PIN 16
#define LORA_CS_PIN 15
#define LORA_RST_PIN 14
#define LORA_DIO0_PIN 13

#endif
