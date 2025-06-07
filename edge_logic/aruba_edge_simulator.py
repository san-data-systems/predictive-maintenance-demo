# edge_logic/aruba_edge_simulator.py

import json
import os
import requests
import paho.mqtt.client as mqtt
import logging
import time

from utilities import get_utc_timestamp, load_app_config, get_full_config

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

        full_cfg_for_globals = get_full_config()
        company_name = full_cfg_for_globals.get('company_name_short', 'DefaultCo')
        
        template = self.config.get('device_id_template')
        num = self.config.get('default_device_id_num')
        if not template or num is None:
             raise KeyError("Missing 'device_id_template' or 'default_device_id_num' in config.")
        self.device_id = template.format(company_name_short=company_name, id=num)
            
        self.thresholds = self.config.get('thresholds')
        if not self.thresholds:
            raise KeyError("Missing 'thresholds' in config.")

        opsramp_cfg = self.config.get('opsramp', {})
        self.opsramp_metrics_endpoint = opsramp_cfg.get('metrics_endpoint')
        self.opsramp_events_endpoint = opsramp_cfg.get('events_endpoint')
        
        self.pcai_trigger_endpoint = os.environ.get(
            'PCAI_AGENT_TRIGGER_ENDPOINT', 
            self.config.get('pcai_agent_trigger_endpoint')
        )
        if not self.pcai_trigger_endpoint:
            raise KeyError("Missing 'pcai_agent_trigger_endpoint' in config or environment variable.")

        print(f"INFO: [{self.device_id}] Aruba Edge Simulator logic initialized.")
        print(f"INFO: [{self.device_id}] PCAI Trigger Endpoint (Actual HTTP): {self.pcai_trigger_endpoint}")

    def _make_actual_api_call(self, endpoint: str, payload: dict, method: str = "POST"):
        print(f"\n--- MAKING ACTUAL HTTP API CALL [{method}] ---")
        print(f"To Endpoint: {endpoint}")
        print(f"Payload:\n{json.dumps(payload, indent=2)}")
        
        response_summary = {"status": "error", "message": "Call not attempted or unknown error"}
        try:
            if method.upper() == "POST":
                response = requests.post(endpoint, json=payload, timeout=300)
            else:
                print(f"ERROR: Unsupported HTTP method '{method}' for API call.")
                return {"status": "error", "message": f"Unsupported HTTP method: {method}"}

            response.raise_for_status() 
            print(f"SUCCESS: API Call to {endpoint} successful. Status: {response.status_code}")
            try:
                response_summary = {"status": "success", "response_data": response.json(), "status_code": response.status_code}
            except requests.exceptions.JSONDecodeError: 
                response_summary = {"status": "success", "response_data": response.text, "status_code": response.status_code}
        except requests.exceptions.RequestException as e:
            print(f"ERROR: API Call to {endpoint} failed: {e}")
            response_summary = {"status": "error", "message": str(e)}
        finally:
            print(f"--- END ACTUAL HTTP API CALL (Status: {response_summary.get('status')}) ---")
        return response_summary

    def _send_metrics_to_opsramp(self, sensor_data: dict):
        metrics_payload = {
            "source_device_id": self.device_id,
            "asset_id": sensor_data["asset_id"],
            "timestamp": sensor_data["timestamp"],
            "metrics": {
                "temperature_c": sensor_data.get("temperature_c"),
                "temperature_increase_c": sensor_data.get("temperature_increase_c"),
                "vibration_overall_amplitude_g": sensor_data.get("vibration_overall_amplitude_g"),
                "vibration_dominant_frequency_hz": sensor_data.get("vibration_dominant_frequency_hz"),
                "acoustic_overall_db": sensor_data.get("acoustic_overall_db"),
                "acoustic_critical_band_db": sensor_data.get("acoustic_critical_band_db"),
            }
        }
        if sensor_data.get("vibration_anomaly_signature_freq_hz") is not None:
            metrics_payload["metrics"]["vibration_anomaly_signature_freq_hz"] = sensor_data["vibration_anomaly_signature_freq_hz"]
            metrics_payload["metrics"]["vibration_anomaly_signature_amp_g"] = sensor_data["vibration_anomaly_signature_amp_g"]
        print(f"\n--- SIMULATING API CALL [POST] (OpsRamp Metrics) ---")
        print(f"To Endpoint: {self.opsramp_metrics_endpoint}")
        print(f"Payload:\n{json.dumps(metrics_payload, indent=2)}")
        print(f"--- END SIMULATED API CALL ---")

    def _detect_gross_anomalies(self, sensor_data: dict) -> list:
        # --- FIX: Restored full dictionary definitions ---
        detected_anomalies = []
        if sensor_data.get("temperature_c", 0) > self.thresholds.get("temperature_critical_c", 999):
            detected_anomalies.append({
                "type": "CriticalTemperature",
                "message": f"Temperature {sensor_data['temperature_c']}°C exceeds threshold of {self.thresholds['temperature_critical_c']}°C.",
                "value": sensor_data["temperature_c"], "threshold": self.thresholds["temperature_critical_c"]
            })
        if sensor_data.get("vibration_anomaly_signature_amp_g") is not None and \
           sensor_data["vibration_anomaly_signature_amp_g"] > self.thresholds.get("vibration_anomaly_amp_g", 999):
            detected_anomalies.append({
                "type": "HighAmplitudeVibrationSignature",
                "message": (f"Vibration anomaly signature {sensor_data['vibration_anomaly_signature_amp_g']}g "
                            f"at {sensor_data['vibration_anomaly_signature_freq_hz']}Hz "
                            f"exceeds threshold of {self.thresholds['vibration_anomaly_amp_g']}g."),
                "anomaly_frequency_hz": sensor_data['vibration_anomaly_signature_freq_hz'],
                "anomaly_amplitude_g": sensor_data['vibration_anomaly_signature_amp_g'],
                "threshold_amp_g": self.thresholds['vibration_anomaly_amp_g']
            })
        if sensor_data.get("acoustic_critical_band_db", 0) > self.thresholds.get("acoustic_critical_band_db", 999):
            detected_anomalies.append({
                "type": "AnomalousAcousticCriticalBand",
                "message": f"Acoustic critical band {sensor_data['acoustic_critical_band_db']}dB exceeds threshold of {self.thresholds['acoustic_critical_band_db']}dB.",
                "value_db": sensor_data["acoustic_critical_band_db"], "threshold_db": self.thresholds['acoustic_critical_band_db']
            })
        return detected_anomalies
        
    def _send_event_to_opsramp(self, sensor_data: dict, anomaly_details: dict):
        event_title = f"Anomalous {anomaly_details['type']} detected on {sensor_data['asset_id']}"
        if anomaly_details['type'] == "HighAmplitudeVibrationSignature": 
             event_title = f"Anomalous vibration pattern detected on {sensor_data['asset_id']}"
        event_payload = {
            "source_id": self.device_id, 
            "resource_id": sensor_data["asset_id"], 
            "timestamp": get_utc_timestamp(), 
            "severity": "CRITICAL", 
            "title": event_title,
            "description": f"Edge logic: {anomaly_details['message']} Escalating to PCAI.",
            "details": {"triggering_anomaly": anomaly_details, "sensor_readings": sensor_data}
        }
        print(f"ALERT: [{self.device_id}] Sending CRITICAL EVENT to OpsRamp: {event_payload['title']}")
        print(f"\n--- SIMULATING API CALL [POST] (OpsRamp Event) ---")
        print(f"To Endpoint: {self.opsramp_events_endpoint}")
        print(f"Payload:\n{json.dumps(event_payload, indent=2)}")
        print(f"--- END SIMULATED API CALL ---")

    def _send_trigger_to_pcai(self, sensor_data: dict, all_detected_anomalies: list):
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
        print(f"\nINFO: [{self.device_id}] Processing data for {sensor_data['asset_id']} at {sensor_data['timestamp']}")
        self._send_metrics_to_opsramp(sensor_data)
        anomalies = self._detect_gross_anomalies(sensor_data)
        if anomalies:
            print(f"WARN: [{self.device_id}] Gross anomalies DETECTED for {sensor_data['asset_id']}:")
            for anomaly in anomalies: 
                print(f"  - Type: {anomaly['type']}, Message: {anomaly['message']}")
            self._send_event_to_opsramp(sensor_data, anomalies[0])
            self._send_trigger_to_pcai(sensor_data, anomalies)
        else:
            print(f"INFO: [{self.device_id}] Data for {sensor_data['asset_id']} within normal edge parameters.")

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
            os._exit(1)
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