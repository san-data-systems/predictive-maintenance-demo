# edge_logic/aruba_edge_simulator.py

import json
import os
import requests
import paho.mqtt.client as mqtt
import logging
import time

from utilities import get_utc_timestamp, load_app_config, get_full_config
from pcai_app.api_connector import OpsRampConnector

logger = logging.getLogger(__name__)

class ArubaEdgeSimulator:
    """
    Simulates an Aruba Edge device that processes sensor data,
    detects gross anomalies, and sends alerts/triggers via actual HTTP calls.
    It is stateful to prevent alert storms to OpsRamp.
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

        # Add state to track if an alert is already active
        self.is_alert_active = False

        # Initialize the OpsRamp Connector to send real alerts
        opsramp_cfg = full_cfg.get('pcai_app', {}).get('opsramp', {})
        self.opsramp_connector = OpsRampConnector(opsramp_config=opsramp_cfg, pcai_agent_id=self.device_id)
        if not self.opsramp_connector.token_url:
            print(f"WARN: [{self.device_id}] OpsRamp connector not fully configured. Real API calls to OpsRamp will be disabled.")
            self.opsramp_connector = None
        else:
            print(f"INFO: [{self.device_id}] OpsRamp Connector Initialized. Will send REAL alerts.")

        print(f"INFO: [{self.device_id}] Aruba Edge Simulator logic initialized.")
        print(f"INFO: [{self.device_id}] PCAI Trigger Endpoint (Actual HTTP): {self.pcai_trigger_endpoint}")


    def _make_actual_api_call(self, endpoint: str, payload: dict, method: str = "POST"):
        """Makes an actual HTTP API call to the PCAI Agent."""
        print(f"\n--- MAKING ACTUAL HTTP API CALL [{method}] ---")
        print(f"To Endpoint: {endpoint}")
        print(f"Payload:\n{json.dumps(payload, indent=2)}")
        
        response_summary = {"status": "error", "message": "Call not attempted or unknown error"}
        try:
            if method.upper() == "POST":
                response = requests.post(endpoint, json=payload, timeout=10)
            else:
                return {"status": "error", "message": f"Unsupported HTTP method: {method}"}

            response.raise_for_status() 
            print(f"SUCCESS: API Call to {endpoint} successful. Status: {response.status_code}")
            response_summary = {"status": "success", "response_data": response.text, "status_code": response.status_code}
        except requests.exceptions.RequestException as e:
            print(f"ERROR: API Call to {endpoint} failed: {e}")
            response_summary = {"status": "error", "message": str(e)}
        finally:
            print(f"--- END ACTUAL HTTP API CALL (Status: {response_summary.get('status')}) ---")
        return response_summary

    def _detect_gross_anomalies(self, sensor_data: dict) -> list:
        """Safely checks sensor data against configured thresholds."""
        detected_anomalies = []
        if sensor_data.get("temperature_c", 0) > self.thresholds.get("temperature_critical_c", 999):
            detected_anomalies.append({
                "type": "CriticalTemperature",
                "message": f"Temperature {sensor_data['temperature_c']}°C exceeds threshold."
            })
        
        anomaly_amp = sensor_data.get("vibration_anomaly_signature_amp_g")
        if anomaly_amp is not None and anomaly_amp > self.thresholds.get("vibration_anomaly_amp_g", 999):
            anomaly_freq = sensor_data.get('vibration_anomaly_signature_freq_hz', 'N/A')
            detected_anomalies.append({
                "type": "HighAmplitudeVibrationSignature",
                "message": f"Vibration anomaly {anomaly_amp}g at {anomaly_freq}Hz exceeds threshold."
            })
        return detected_anomalies
        
    def _send_event_to_opsramp(self, sensor_data: dict, anomaly_details: dict):
        """Sends a single, real CRITICAL alert to OpsRamp."""
        if not self.opsramp_connector:
            print("INFO: OpsRamp connector not configured, skipping alert.")
            return

        event_title = f"Edge Detection: {anomaly_details['type']} on {sensor_data['asset_id']}"
        description = f"Edge logic: {anomaly_details['message']} Escalating to PCAI."
        
        self.opsramp_connector.send_pcai_log(
            asset_id=sensor_data["asset_id"],
            log_level="CRITICAL",
            message=event_title,
            details={"triggering_anomaly": anomaly_details}
        )

    def _send_trigger_to_pcai(self, sensor_data: dict, all_detected_anomalies: list):
        """Sends the trigger payload to the PCAI Agent application."""
        pcai_trigger_payload = {
            "source_component": self.device_id, 
            "asset_id": sensor_data["asset_id"],
            "trigger_timestamp": get_utc_timestamp(), 
            "edge_detected_anomalies": all_detected_anomalies, 
            "full_sensor_data_at_trigger": sensor_data 
        }
        print(f"INFO: [{self.device_id}] Preparing to send Anomaly Trigger to PCAI for {sensor_data['asset_id']}")
        self._make_actual_api_call(self.pcai_trigger_endpoint, pcai_trigger_payload, method="POST")

    def process_sensor_data(self, sensor_data: dict):
        """
        Main processing logic. Detects anomalies and sends alerts only when the state changes.
        """
        anomalies = self._detect_gross_anomalies(sensor_data)
        
        if anomalies and not self.is_alert_active:
            # If we find anomalies AND an alert is not already active...
            self.is_alert_active = True # Set the flag to prevent re-alerting
            print(f"WARN: [{self.device_id}] NEW Gross anomaly detected. State set to ACTIVE.")
            # Send one alert to OpsRamp and one trigger to PCAI
            self._send_event_to_opsramp(sensor_data, anomalies[0])
            self._send_trigger_to_pcai(sensor_data, anomalies)

        elif not anomalies and self.is_alert_active:
            # If data is normal AND an alert was previously active, reset the flag
            self.is_alert_active = False
            print(f"INFO: [{self.device_id}] Anomaly condition cleared. State set to INACTIVE.")
            # Optionally, send a "CLEAR" event to OpsRamp here
        
        else:
            # Otherwise, just log that we are processing normally
            status = "Anomalous" if self.is_alert_active else "Normal"
            print(f"INFO: [{self.device_id}] Data for {sensor_data['asset_id']} processed. Current State: {status}")

if __name__ == "__main__":
    config = get_full_config()
    if not config:
        print("FATAL: Could not load configuration. Exiting.")
        exit(1)
    mqtt_config = config.get('mqtt', {})
    broker_hostname = os.environ.get("MQTT_BROKER_HOSTNAME", mqtt_config.get('broker_hostname', 'localhost'))
    broker_port = int(os.environ.get("MQTT_BROKER_PORT", mqtt_config.get('broker_port', 1883)))
    topic = mqtt_config.get('sensor_topic', 'hpe/demo/default/sensors')

    try:
        edge_sim = ArubaEdgeSimulator()
    except (ValueError, KeyError) as e:
        print(f"FATAL: Could not initialize ArubaEdgeSimulator. Exiting. Error: {e}")
        exit(1)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"Failed to connect to MQTT Broker: {reason_code}. Exiting.")
            os._exit(1) # Use os._exit in a threaded context to force exit
        else:
            print(f"Successfully connected to MQTT Broker. Subscribing to topic: '{topic}'")
            client.subscribe(topic)

    def on_message(client, userdata, msg):
        print(f"\n--- MQTT message received on topic '{msg.topic}' ---")
        try:
            payload_str = msg.payload.decode('utf-8')
            sensor_data = json.loads(payload_str)
            edge_sim.process_sensor_data(sensor_data)
        except json.JSONDecodeError:
            print(f"ERROR: Could not decode JSON from payload: {msg.payload}")
        except Exception as e:
            print(f"ERROR: An error occurred processing message: {e}", exc_info=True)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aruba-edge-simulator-01")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    print(f"--- Starting Aruba Edge Simulator as MQTT Subscriber ---")
    print(f"  Connecting to MQTT Broker: {broker_hostname}:{broker_port}")
    
    try:
        mqtt_client.connect(broker_hostname, broker_port, 60)
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        print("\nINFO: Edge Simulator stopped by user.")
    except Exception as e:
        print(f"An unexpected error occurred in Edge Simulator's main loop: {e}", exc_info=True)
    finally:
        mqtt_client.disconnect()
        print("INFO: MQTT client disconnected.")