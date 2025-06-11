# iot_sensor_simulator.py

import paho.mqtt.client as mqtt
import time
import json
import logging
import random
from datetime import datetime, timezone

# Use the decoupled configuration loader from the utilities package
from utilities.common_utils import get_full_config

class TurbineSensor:
    """
    Simulates a sensor on an industrial asset, generating operational data
    and capable of simulating anomalous behavior.
    """
    def __init__(self, config):
        self.asset_id = config.get('asset_id', 'Default_Asset_ID')
        self.base_temp = config.get('base_temperature', 42.0)
        self.vib_norm = config.get('vibration_normal_range', [0.1, 0.5])
        self.acou_norm = config.get('acoustic_normal_range', [20.0, 35.0])
        self.anomaly_start_chance = config.get('anomaly_start_chance', 0.15)
        self.anomaly_stop_chance = config.get('anomaly_stop_chance', 0.4)
        self.anomaly_vib_factor = config.get('anomaly_vibration_factor', 10.0)
        self.is_anomaly = False
        logging.info(f"[Sensor Simulation | {self.asset_id}] Initialized.")

    def generate_data(self):
        # Decide whether to start or stop an anomaly
        if not self.is_anomaly and random.random() < self.anomaly_start_chance:
            self.is_anomaly = True
            logging.warning(f"[Sensor Simulation | {self.asset_id}] >>> Anomaly Injected! <<<")
        elif self.is_anomaly and random.random() < self.anomaly_stop_chance:
            self.is_anomaly = False
            logging.info(f"[Sensor Simulation | {self.asset_id}] Anomaly resolved. Returning to normal operations.")

        # Generate data based on state (normal or anomaly)
        if self.is_anomaly:
            vibration = random.uniform(self.vib_norm[0], self.vib_norm[1]) * self.anomaly_vib_factor
            temperature = self.base_temp + random.uniform(5.0, 15.0)
            acoustic = random.uniform(self.acou_norm[0], self.acou_norm[1]) * 1.5
            status = "WARNING"
        else:
            vibration = random.uniform(self.vib_norm[0], self.vib_norm[1])
            temperature = self.base_temp + random.uniform(-1.0, 1.0)
            acoustic = random.uniform(self.acou_norm[0], self.acou_norm[1])
            status = "NORMAL"
            
        return round(vibration, 4), round(temperature, 4), round(acoustic, 4), status, self.is_anomaly

def setup_mqtt_client(client_id_prefix, config):
    """Initializes and configures a Paho MQTT client object but does not connect."""
    client_id = "" if client_id_prefix == "ThingsBoard" else f"{client_id_prefix}-{int(time.time())}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    
    if config.get('device_token') and config.get('device_token') != 'YOUR_THINGSBOARD_DEVICE_TOKEN' and config.get('device_token') != 'PASTE_YOUR_REAL_THINGSBOARD_TOKEN_HERE':
        client.username_pw_set(config['device_token'])
        
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logging.warning(f"MQTT | Client '{client_id_prefix}' failed to connect: {reason_code}.")
        else:
            logging.info(f"MQTT | Client '{client_id_prefix}' successfully connected.")

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        if reason_code and not reason_code.is_failure:
             logging.info(f"MQTT | Client '{client_id_prefix}' disconnected cleanly.")
        else:
            logging.warning(f"MQTT | Client '{client_id_prefix}' unexpectedly disconnected: {reason_code}. Will try to reconnect.")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    return client

def attempt_reconnect(client, client_name, config):
    """Attempts to connect a client if it's not already connected."""
    if not client.is_connected():
        try:
            logging.info(f"MQTT | Attempting to connect client '{client_name}' to {config['host']}:{config['port']}...")
            client.connect_async(config['host'], config['port'], 60)
        except Exception as e:
            logging.error(f"MQTT | Error while trying to connect client '{client_name}': {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)-8s - %(name)-15s - %(message)s')
    logger = logging.getLogger(__name__)

    full_config = get_full_config()
    if not full_config:
        logger.critical("FATAL: Could not load configuration. Exiting.")
        exit(1)
        
    sensor_config_from_yaml = full_config.get('iot_sensor_simulator', {})
    internal_cfg = full_config.get('mqtt', {})
    tb_cfg = full_config.get('thingsboard', {})
    company_name = full_config.get('company_name_short', 'DefaultCo')
    
    asset_id = sensor_config_from_yaml.get('asset_id_prefix', "{company_name_short}_Turbine").format(company_name_short=company_name)
    asset_id += str(sensor_config_from_yaml.get('default_asset_number', 7)).zfill(3)

    sensor_constructor_config = {
        'asset_id': asset_id,
        'base_temperature': sensor_config_from_yaml.get('base_temp_c', 42.0),
        'vibration_normal_range': sensor_config_from_yaml.get('vibration_normal_range', [0.1, 0.5]),
        'acoustic_normal_range': sensor_config_from_yaml.get('acoustic_normal_range', [20.0, 35.0]),
        'anomaly_start_chance': sensor_config_from_yaml.get('anomaly_start_chance', 0.15),
        'anomaly_stop_chance': sensor_config_from_yaml.get('anomaly_stop_chance', 0.4),
        'anomaly_vibration_factor': sensor_config_from_yaml.get('anomaly_vibration_factor', 10.0)
    }
    sensor = TurbineSensor(config=sensor_constructor_config)

    logger.info("--- Initializing MQTT clients in disconnected state ---")
    internal_mqtt_client = setup_mqtt_client("Internal", internal_cfg)
    thingsboard_mqtt_client = setup_mqtt_client("ThingsBoard", tb_cfg)
    
    internal_mqtt_client.loop_start()
    thingsboard_mqtt_client.loop_start()
    logger.info("--- Starting IoT Sensor Simulation (Press Ctrl+C to stop) ---")

    while True:
        try:
            vibration, temperature, acoustic, status, anomaly_injected = sensor.generate_data()
            timestamp = datetime.now(timezone.utc).isoformat()
            
            internal_payload_dict = {
                "assetId": sensor.asset_id,
                "timestamp": timestamp,
                "vibration": vibration,
                "temperature": temperature,
                "acoustic": acoustic,
                "status": status,
                "anomalyInjected": anomaly_injected
            }
            internal_payload_json = json.dumps(internal_payload_dict)
            
            logger.info(f"SENSOR | Generated data: Temp={temperature:.2f}°C, Vib={vibration:.2f}g, Status={status}")

            thingsboard_payload_dict = {
                "temperature_c": temperature,
                "acoustic_critical_band_db": acoustic,
                "is_anomaly_induced": "true" if anomaly_injected else "false",
                "temperature_increase_c": max(0, temperature - sensor.base_temp),
                "vibration_overall_amplitude_g": vibration,
                "vibration_dominant_frequency_hz": random.uniform(55, 65) if not anomaly_injected else 120.5,
                "vibration_anomaly_signature_amp_g": vibration if anomaly_injected else 0.0,
                "vibration_anomaly_signature_freq_hz": 120.5 if anomaly_injected else 0.0
            }
            thingsboard_payload_json = json.dumps(thingsboard_payload_dict)

            attempt_reconnect(internal_mqtt_client, "Internal", internal_cfg)
            if internal_mqtt_client.is_connected():
                internal_mqtt_client.publish(internal_cfg['sensor_topic'], internal_payload_json, qos=1)
                logger.info("MQTT | Published to Internal broker.")
            else:
                logger.warning("MQTT | Internal broker not connected. Skipping publish.")

            attempt_reconnect(thingsboard_mqtt_client, "ThingsBoard", tb_cfg)
            if thingsboard_mqtt_client.is_connected():
                thingsboard_mqtt_client.publish('v1/devices/me/telemetry', thingsboard_payload_json, qos=1)
                logger.info("MQTT | Published detailed payload to ThingsBoard broker.")
            else:
                logger.warning("MQTT | ThingsBoard broker not connected. Skipping publish.")

            time.sleep(sensor_config_from_yaml.get('data_interval_seconds', 5))
        except KeyboardInterrupt:
            logger.info("--- Simulation stopped by user ---")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            time.sleep(5)

    logger.info("--- Shutting down MQTT clients ---")
    internal_mqtt_client.loop_stop()
    thingsboard_mqtt_client.loop_stop()
    if internal_mqtt_client.is_connected():
        internal_mqtt_client.disconnect()
    if thingsboard_mqtt_client.is_connected():
        thingsboard_mqtt_client.disconnect()
    logger.info("--- Shutdown complete ---")