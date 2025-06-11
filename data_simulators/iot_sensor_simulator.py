# iot_sensor_simulator.py

import paho.mqtt.client as mqtt
import time
import json
import logging
import sys
import random
from datetime import datetime, timezone

# Assume these utilities exist in your project structure
# from utilities.config_loader import load_config
# from utilities.logging_setup import setup_logging

# ==============================================================================
#  Placeholder for Utility Functions (for standalone testing)
# ==============================================================================

def setup_logging():
    """Basic logging setup if utility is not available."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def load_config():
    """Basic config loading if utility is not available."""
    logging.info("Using placeholder configuration.")
    return {
        'iot_sensor': {
            'asset_id': 'DemoCorp_Turbine_007',
            'base_temperature': 42.0,
            'vibration_normal_range': [0.1, 0.5],
            'acoustic_normal_range': [20.0, 35.0],
            'anomaly_start_chance': 0.15,
            'anomaly_stop_chance': 0.4,
            'anomaly_vibration_factor': 10.0,
            'simulation_interval_seconds': 5
        },
        'internal_mqtt': {
            'host': 'localhost',
            'port': 1883,
            'topic': 'hpe/demo/turbine/007/sensors'
        },
        'thingsboard_mqtt': {
            'host': 'localhost',
            'port': 1884,
            'device_token': 'YVeoL2kBuBjrtv8Bqb9hK'
        }
    }

# ==============================================================================
#  TurbineSensor Class
# ==============================================================================

class TurbineSensor:
    """
    Simulates a sensor on an industrial asset, generating operational data
    and capable of simulating anomalous behavior.
    """
    def __init__(self, config):
        self.asset_id = config['asset_id']
        self.base_temp = config['base_temperature']
        self.vib_norm = config['vibration_normal_range']
        self.acou_norm = config['acoustic_normal_range']
        self.anomaly_start_chance = config['anomaly_start_chance']
        self.anomaly_stop_chance = config['anomaly_stop_chance']
        self.anomaly_vib_factor = config['anomaly_vibration_factor']
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
            temperature = self.base_temp + random.uniform(5.0, 15.0) # Temp rises during anomaly
            acoustic = random.uniform(self.acou_norm[0], self.acou_norm[1]) * 1.5
            status = "WARNING"
        else:
            vibration = random.uniform(self.vib_norm[0], self.vib_norm[1])
            temperature = self.base_temp + random.uniform(-1.0, 1.0)
            acoustic = random.uniform(self.acou_norm[0], self.acou_norm[1])
            status = "NORMAL"
            
        return round(vibration, 4), round(temperature, 4), round(acoustic, 4), status, self.is_anomaly

# ==============================================================================
#  MQTT Client Handling Functions (Corrected Version)
# ==============================================================================

def setup_mqtt_client(client_id_prefix, config):
    """Initializes and configures a Paho MQTT client object but does not connect."""
    
    # If connecting to ThingsBoard, the client_id must be empty.
    # For other brokers (like our internal one), a unique ID is good practice.
    client_id = "" if client_id_prefix == "ThingsBoard" else f"{client_id_prefix}-{int(time.time())}"
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    
    if config.get('device_token') and config['device_token'] != 'YOUR_THINGSBOARD_DEVICE_TOKEN':
        client.username_pw_set(config['device_token'])
        
    # Updated on_connect signature to use 'reason_code' for clarity.
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logging.warning(f"MQTT | Client '{client_id_prefix}' failed to connect: {reason_code}.")
        else:
            logging.info(f"MQTT | Client '{client_id_prefix}' successfully connected.")

    # Updated on_disconnect signature to accept all 5 arguments.
    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        # A reason_code of 0 indicates a clean disconnect.
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
            # Use connect_async to avoid blocking the main loop
            client.connect_async(config['host'], config['port'], 60)
        except Exception as e:
            logging.error(f"MQTT | Error while trying to connect client '{client_name}': {e}")

# ==============================================================================
#  Main Execution Block
# ==============================================================================

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    config = load_config()
    sensor_config = config['iot_sensor']
    sensor = TurbineSensor(config=sensor_config)

    # --- 1. Initialize Clients (but do not connect yet) ---
    logger.info("--- Initializing MQTT clients in disconnected state ---")
    internal_cfg = config['internal_mqtt']
    tb_cfg = config['thingsboard_mqtt']

    internal_mqtt_client = setup_mqtt_client("Internal", internal_cfg)
    thingsboard_mqtt_client = setup_mqtt_client("ThingsBoard", tb_cfg)
    
    # Start the network loops in the background. This handles message queues and reconnects.
    internal_mqtt_client.loop_start()
    thingsboard_mqtt_client.loop_start()

    logger.info("--- Starting IoT Sensor Simulation (Press Ctrl+C to stop) ---")

    # --- 2. Main Resilient Loop ---
    while True:
        try:
            # Step A: Always generate data, regardless of network state
            vibration, temperature, acoustic, status, anomaly_injected = sensor.generate_data()
            timestamp = datetime.now(timezone.utc).isoformat()
            
            payload_dict = {
                "assetId": sensor.asset_id, "timestamp": timestamp, "vibration": vibration,
                "temperature": temperature, "acoustic": acoustic, "status": status,
                "anomalyInjected": anomaly_injected
            }
            payload_json = json.dumps(payload_dict)
            
            logger.info(f"SENSOR | Generated data: Temp={temperature:.2f}°C, Vib={vibration:.2f}g, Status={status}")

            # Step B: Attempt to reconnect and publish for each client
            
            # -- Internal Client --
            attempt_reconnect(internal_mqtt_client, "Internal", internal_cfg)
            if internal_mqtt_client.is_connected():
                internal_mqtt_client.publish(internal_cfg['topic'], payload_json, qos=1)
                logger.info("MQTT | Published to Internal broker.")
            else:
                logger.warning("MQTT | Internal broker not connected. Skipping publish.")

            # -- ThingsBoard Client --
            attempt_reconnect(thingsboard_mqtt_client, "ThingsBoard", tb_cfg)
            if thingsboard_mqtt_client.is_connected():
                tb_payload = json.dumps({"vibration": vibration, "temperature": temperature, "acoustic": acoustic})
                thingsboard_mqtt_client.publish('v1/devices/me/telemetry', tb_payload, qos=1)
                logger.info("MQTT | Published to ThingsBoard broker.")
            else:
                logger.warning("MQTT | ThingsBoard broker not connected. Skipping publish.")

            # Step C: Wait for the next cycle
            time.sleep(sensor_config['simulation_interval_seconds'])

        except KeyboardInterrupt:
            logger.info("--- Simulation stopped by user ---")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            # Even with other errors, we wait and continue, making it very resilient.
            time.sleep(sensor_config['simulation_interval_seconds'])

    # --- 3. Graceful Cleanup ---
    logger.info("--- Shutting down MQTT clients ---")
    internal_mqtt_client.loop_stop()
    thingsboard_mqtt_client.loop_stop()
    if internal_mqtt_client.is_connected():
        internal_mqtt_client.disconnect()
    if thingsboard_mqtt_client.is_connected():
        thingsboard_mqtt_client.disconnect()
    logger.info("--- Shutdown complete ---")