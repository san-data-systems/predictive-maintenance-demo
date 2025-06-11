# edge_logic/aruba_edge_simulator.py

import json
import os
import requests
import paho.mqtt.client as mqtt
import logging
import time

# Assuming these utilities are in the parent directory or PYTHONPATH
from utilities.common_utils import get_utc_timestamp, load_app_config, get_full_config
from pcai_app.api_connector import OpsRampConnector

# Use the logger for all output
logger = logging.getLogger(__name__)

class ArubaEdgeSimulator:
    """
    Simulates an Aruba Edge device that processes sensor data,
    detects gross anomalies, and sends alerts/triggers via actual HTTP calls.
    """
    def __init__(self):
        self.config = load_app_config('aruba_edge_simulator')
        if not self.config:
            raise ValueError("Failed to load 'aruba_edge_simulator' configuration section.")

        full_cfg = get_full_config()
        company_name = full_cfg.get('company_name_short', 'DefaultCo')
        
        template = self.config.get('device_id_template')
        num = self.config.get('default_device_id_num')
        self.device_id = template.format(company_name_short=company_name, id=num)
            
        self.thresholds = self.config.get('thresholds')
        if not self.thresholds:
            raise KeyError("Missing 'thresholds' in config.")
        
        self.pcai_trigger_endpoint = os.environ.get(
            'PCAI_AGENT_TRIGGER_ENDPOINT', 
            self.config.get('pcai_agent_trigger_endpoint')
        )
        self.is_alert_active = False

        opsramp_cfg = full_cfg.get('pcai_app', {}).get('opsramp', {})
        self.opsramp_connector = OpsRampConnector(opsramp_config=opsramp_cfg, pcai_agent_id=self.device_id)
        if not self.opsramp_connector.token_url:
            logger.warning(f"[{self.device_id}] OpsRamp connector not fully configured. API calls to OpsRamp will be disabled.")
            self.opsramp_connector = None
        else:
            logger.info(f"[{self.device_id}] OpsRamp Connector Initialized. Will send REAL alerts.")

        logger.info(f"[{self.device_id}] Aruba Edge Simulator logic initialized.")
        logger.info(f"[{self.device_id}] PCAI Trigger Endpoint (Actual HTTP): {self.pcai_trigger_endpoint}")

    def _make_actual_api_call(self, endpoint: str, payload: dict, method: str = "POST"):
        """Makes an actual HTTP API call to the PCAI Agent."""
        logger.info(f"--- MAKING ACTUAL HTTP API CALL [{method}] ---")
        logger.info(f"To Endpoint: {endpoint}")
        
        try:
            response = requests.post(endpoint, json=payload, timeout=10)
            response.raise_for_status() 
            logger.info(f"SUCCESS: API Call to {endpoint} successful. Status: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"ERROR: API Call to {endpoint} failed: {e}")
        finally:
            logger.info(f"--- END ACTUAL HTTP API CALL ---")

    def _detect_gross_anomalies(self, sensor_data: dict) -> list:
        """Safely checks sensor data against configured thresholds."""
        detected_anomalies = []
        # FIX: Use 'temperature' from the payload, not 'temperature_c'
        if sensor_data.get("temperature", 0) > self.thresholds.get("temperature_critical_c", 999):
            detected_anomalies.append({
                "type": "CriticalTemperature",
                "message": f"Temperature {sensor_data['temperature']}°C exceeds threshold."
            })
        
        # FIX: Check for 'vibration' key
        if sensor_data.get("vibration", 0) > self.thresholds.get("vibration_anomaly_amp_g", 999):
            detected_anomalies.append({
                "type": "HighAmplitudeVibration",
                "message": f"Vibration anomaly {sensor_data['vibration']}g exceeds threshold."
            })
        return detected_anomalies
        
    def _send_event_to_opsramp(self, sensor_data: dict, anomaly_details: dict):
        """Sends a single, real CRITICAL alert to OpsRamp."""
        if not self.opsramp_connector:
            logger.info("OpsRamp connector not configured, skipping alert.")
            return

        # FIX: Use 'assetId' from the payload
        event_title = f"Edge Detection: {anomaly_details['type']} on {sensor_data['assetId']}"
        description = f"Edge logic: {anomaly_details['message']} Escalating to PCAI."
        
        self.opsramp_connector.send_pcai_log(
            asset_id=sensor_data["assetId"],
            log_level="CRITICAL",
            message=event_title,
            details={"triggering_anomaly": anomaly_details}
        )

    def _send_trigger_to_pcai(self, sensor_data: dict, all_detected_anomalies: list):
        """Sends the trigger payload to the PCAI Agent application."""
        pcai_trigger_payload = {
            "source_component": self.device_id,
            # FIX: Use 'assetId' from the payload
            "asset_id": sensor_data["assetId"],
            "trigger_timestamp": get_utc_timestamp(), 
            "edge_detected_anomalies": all_detected_anomalies, 
            "full_sensor_data_at_trigger": sensor_data 
        }
        logger.info(f"[{self.device_id}] Preparing to send Anomaly Trigger to PCAI for {sensor_data['assetId']}")
        self._make_actual_api_call(self.pcai_trigger_endpoint, pcai_trigger_payload, method="POST")

    def process_sensor_data(self, sensor_data: dict):
        """
        Main processing logic. Detects anomalies and now sends logs for ALL messages.
        """
        asset_id = sensor_data.get("assetId", "UnknownAsset")
        anomalies = self._detect_gross_anomalies(sensor_data)
        
        if anomalies and not self.is_alert_active:
            # If we find anomalies AND an alert is not already active...
            self.is_alert_active = True # Set the flag to prevent re-alerting
            logger.warning(f"[{self.device_id}] NEW Gross anomaly detected on {asset_id}. State set to ACTIVE.")
            # Send one alert to OpsRamp and one trigger to PCAI
            self._send_event_to_opsramp(sensor_data, anomalies[0])
            self._send_trigger_to_pcai(sensor_data, anomalies)

        elif not anomalies and self.is_alert_active:
            # If data is normal AND an alert was previously active, reset the flag
            self.is_alert_active = False
            logger.info(f"[{self.device_id}] Anomaly condition cleared on {asset_id}. State set to INACTIVE.")
            # Optionally, send a "CLEAR" event to OpsRamp here
            if self.opsramp_connector:
                self.opsramp_connector.send_pcai_log(
                    asset_id=asset_id,
                    log_level="INFO",
                    message=f"Edge Event: Anomaly Condition Cleared on {asset_id}",
                    details={"status": "Normal", "message": "Returning to normal operations."}
                )
        
        else:
            # This block now sends an INFO log for every normal message
            status = "Anomalous" if self.is_alert_active else "Normal"
            logger.info(f"[{self.device_id}] Data for {asset_id} processed. Current State: {status}")
            if not self.is_alert_active and self.opsramp_connector:
                 self.opsramp_connector.send_pcai_log(
                    asset_id=asset_id,
                    log_level="INFO",
                    message=f"Edge Event: Normal operation for {asset_id}",
                    details=sensor_data
                )

if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)-8s - %(name)-15s - %(message)s')

    config = get_full_config()
    if not config:
        logger.critical("FATAL: Could not load configuration. Exiting.")
        exit(1)
        
    mqtt_config = config.get('mqtt', {})
    broker_hostname = os.environ.get("MQTT_BROKER_HOSTNAME", mqtt_config.get('host', 'localhost'))
    broker_port = int(os.environ.get("MQTT_BROKER_PORT", mqtt_config.get('port', 1883)))
    topic = mqtt_config.get('sensor_topic', 'hpe/demo/default/sensors')

    try:
        edge_sim = ArubaEdgeSimulator()
    except (ValueError, KeyError) as e:
        logger.critical(f"FATAL: Could not initialize ArubaEdgeSimulator. Exiting. Error: {e}", exc_info=True)
        exit(1)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logger.error(f"Failed to connect to MQTT Broker: {reason_code}. Exiting.")
            os._exit(1) 
        else:
            logger.info(f"Successfully connected to MQTT Broker. Subscribing to topic: '{topic}'")
            client.subscribe(topic)

    def on_message(client, userdata, msg):
        logger.info(f"--- MQTT message received on topic '{msg.topic}' ---")
        try:
            payload_str = msg.payload.decode('utf-8')
            sensor_data = json.loads(payload_str)
            edge_sim.process_sensor_data(sensor_data)
        except json.JSONDecodeError:
            # FIX: Use logger to correctly show exception info
            logger.error(f"Could not decode JSON from payload: {msg.payload}", exc_info=True)
        except Exception as e:
            logger.error(f"An error occurred processing message: {e}", exc_info=True)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aruba-edge-simulator-01")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    logger.info("--- Starting Aruba Edge Simulator as MQTT Subscriber ---")
    logger.info(f"  Connecting to MQTT Broker: {broker_hostname}:{broker_port}")
    
    try:
        mqtt_client.connect(broker_hostname, broker_port, 60)
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        logger.info("\nEdge Simulator stopped by user.")
    except Exception as e:
        # FIX: Use logger to correctly show exception info
        logger.critical(f"An unexpected error occurred in Edge Simulator's main loop: {e}", exc_info=True)
    finally:
        mqtt_client.disconnect()
        logger.info("MQTT client disconnected.")