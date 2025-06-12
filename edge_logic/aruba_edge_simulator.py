# edge_logic/aruba_edge_simulator.py

import json
import os
import requests
import paho.mqtt.client as mqtt
import logging
import time

from utilities.common_utils import get_utc_timestamp, load_app_config, get_full_config
from utilities.api_connector import OpsRampConnector

# Configure logging for the module
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

        self.thresholds = self.config.get('thresholds', {}) 
        if not self.thresholds:
            logger.warning("Missing 'thresholds' section in aruba_edge_simulator config. Using default detection thresholds.")
            self.thresholds = {
                "temperature_critical_c": 55,
                "vibration_anomaly_freq_hz": 120,
                "vibration_amplitude_gross_g": 1.5
            }

        self.pcai_trigger_endpoint = os.environ.get(
            'PCAI_AGENT_TRIGGER_ENDPOINT', 
            self.config.get('pcai_agent_trigger_endpoint')
        )
        self.is_alert_active = False 

        opsramp_cfg = full_cfg.get('pcai_app', {}).get('opsramp', {})
        connector = OpsRampConnector(opsramp_config=opsramp_cfg, pcai_agent_id=self.device_id)
        if not getattr(connector, 'token_url', None):
            logger.warning(f"[{self.device_id}] OpsRamp connector not fully configured. Alerts disabled.")
            self.opsramp_connector = None
        else:
            self.opsramp_connector = connector
            logger.info(f"[{self.device_id}] OpsRamp Connector initialized.")

        logger.info(f"[{self.device_id}] Aruba Edge Simulator initialized.")
        logger.info(f"[{self.device_id}] PCAI Trigger Endpoint: {self.pcai_trigger_endpoint}")

    def _make_actual_api_call(self, endpoint: str, payload: dict, method: str = "POST"):
        """Makes an actual HTTP API call (e.g., to the PCAI Agent)."""
        logger.info(f"--- MAKING ACTUAL HTTP API CALL [{method}] ---")
        logger.info(f"To Endpoint: {endpoint}")
        try:
            response = requests.post(endpoint, json=payload, timeout=60) 
            response.raise_for_status() 
            logger.info(f"SUCCESS: API Call to {endpoint}. Status: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"ERROR: API Call to {endpoint} failed: {e}")
        finally:
            logger.info(f"--- END ACTUAL HTTP API CALL ---")

    def _detect_gross_anomalies(self, sensor_data: dict) -> list:
        """
        Checks sensor data against configured thresholds to detect gross anomalies.
        Returns a list of detected anomalies.
        """
        detected_anomalies = []
        
        temp_threshold = self.thresholds.get("temperature_critical_c", 55)
        if sensor_data.get("temperature", 0) > temp_threshold:
            detected_anomalies.append({
                "type": "CriticalTemperature",
                "message": f"Temperature {sensor_data['temperature']:.2f}°C exceeds threshold ({temp_threshold}°C)."
            })

        freq_threshold = self.thresholds.get("vibration_anomaly_freq_hz", 120)
        if sensor_data.get("vibration_dominant_frequency_hz", 0) > freq_threshold:
            detected_anomalies.append({
                "type": "HighFrequencyVibration",
                "message": f"Dominant vibration frequency {sensor_data['vibration_dominant_frequency_hz']:.2f}Hz exceeds threshold ({freq_threshold}Hz)."
            })
        
        amp_threshold = self.thresholds.get("vibration_amplitude_gross_g", 1.5)
        if sensor_data.get("vibration_overall_amplitude_g", 0) > amp_threshold:
             detected_anomalies.append({
                "type": "HighAmplitudeVibration",
                "message": f"Overall vibration amplitude {sensor_data['vibration_overall_amplitude_g']:.2f}g exceeds threshold ({amp_threshold}g)."
            })

        return detected_anomalies

    def _send_event_to_opsramp(self, sensor_data: dict, anomaly: dict):
        """Sends a specific event/alert to OpsRamp via the connector."""
        if not self.opsramp_connector:
            logger.info("OpsRamp connector disabled or not configured. Skipping alert.")
            return
        
        title = f"Edge Detection: {anomaly['type']} on {sensor_data['assetId']}"
        message_details = {
            "triggering_anomaly": anomaly,
            "sensor_data_snapshot": {
                "vibration": sensor_data.get("vibration_overall_amplitude_g"),
                "temperature": sensor_data.get("temperature"),
                "acoustic": sensor_data.get("acoustic_critical_band_db"),
                "dominant_freq": sensor_data.get("vibration_dominant_frequency_hz")
            }
        }
        
        self.opsramp_connector.send_pcai_log(
            asset_id=sensor_data["assetId"],
            log_level="CRITICAL",
            message=title,
            details=message_details
        )

    def _send_trigger_to_pcai(self, sensor_data: dict, anomalies: list):
        """Sends a detailed trigger payload to the PCAI Agent for deeper analysis."""
        payload = {
            "source_component": self.device_id,
            "asset_id": sensor_data.get("assetId"),
            "trigger_timestamp": get_utc_timestamp(),
            "edge_detected_anomalies": anomalies,
            "full_sensor_data_at_trigger": sensor_data
        }
        logger.info(f"[{self.device_id}] Sending trigger to PCAI for {sensor_data.get('assetId')}")
        self._make_actual_api_call(self.pcai_trigger_endpoint, payload)

    def process_sensor_data(self, sensor_data: dict):
        """
        Main method to process incoming sensor data.
        Detects anomalies and sends alerts ONLY when a new anomaly is found.
        """
        asset_id = sensor_data.get("assetId", "UnknownAsset")
        anomalies = self._detect_gross_anomalies(sensor_data)

        logger.info(f"[{self.device_id}] Processing data for {asset_id} at {sensor_data.get('timestamp', 'N/A')}")

        # --- MODIFICATION START ---
        # This logic is now simpler. It only acts if an anomaly is found
        # and an alert is not already active for this session.
        if anomalies and not self.is_alert_active:
            self.is_alert_active = True
            logger.warning(f"[{self.device_id}] Gross anomalies DETECTED on {asset_id}. Triggering CRITICAL alert to OpsRamp.")
            # Send the critical alert to OpsRamp
            self._send_event_to_opsramp(sensor_data, anomalies[0]) 
            # Send the trigger to the PCAI agent for analysis
            self._send_trigger_to_pcai(sensor_data, anomalies)

        # If there are no anomalies, we must reset the alert flag so it can fire again if needed.
        elif not anomalies and self.is_alert_active:
            self.is_alert_active = False
            # The notification to OpsRamp about the clear condition has been removed as requested.
            logger.info(f"[{self.device_id}] Anomaly cleared on {asset_id}. Resetting alert flag. No 'clear' event will be sent to OpsRamp.")
        
        else:
            # During normal operation or an ongoing (already reported) anomaly, just log to the console.
            status = "Anomalous (already reported)" if self.is_alert_active else "Normal"
            logger.info(f"[{self.device_id}] Data processed for {asset_id}. State: {status}. No new event will be sent to OpsRamp.")
        # --- MODIFICATION END ---


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)-8s - %(name)-15s - %(message)s')
    
    config = get_full_config()
    if not config:
        logger.critical("FATAL: Could not load configuration. Exiting.")
        exit(1)

    mqtt_cfg = config.get('mqtt', {})
    broker = os.environ.get("MQTT_BROKER_HOSTNAME", mqtt_cfg.get('host', 'localhost'))
    port = int(os.environ.get("MQTT_BROKER_PORT", mqtt_cfg.get('port', 1883)))
    topic = mqtt_cfg.get('sensor_topic', 'hpe/demo/default/sensors')

    try:
        simulator = ArubaEdgeSimulator()
    except (ValueError, KeyError) as e:
        logger.critical(f"FATAL: Edge Simulator initialization error: {e}", exc_info=True)
        exit(1)

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc != 0:
            logger.error(f"Failed to connect to MQTT Broker: {rc}")
            os._exit(1) 
        logger.info(f"Connected to MQTT Broker. Subscribing to {topic}")
        client.subscribe(topic)

    def on_message(client, userdata, msg):
        logger.info(f"MQTT message received on '{msg.topic}'")
        try:
            data = json.loads(msg.payload.decode()) 
            simulator.process_sensor_data(data) 
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {msg.payload}", exc_info=True)
        except Exception as ex:
            logger.error(f"Error processing MQTT message: {ex}", exc_info=True)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aruba-edge-simulator")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    logger.info(f"Starting MQTT subscriber at {broker}:{port}")
    try:
        mqtt_client.connect(broker, port, keepalive=60)
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Simulator stopped by user (Ctrl+C).")
    except Exception as err:
        logger.critical(f"Simulator experienced an unexpected error: {err}", exc_info=True)
    finally:
        mqtt_client.disconnect()
        logger.info("MQTT client disconnected.")