# edge_logic/aruba_edge_simulator.py

import json
import time
import os
import requests 

from utilities import get_utc_timestamp, load_app_config, get_full_config
from data_simulators.iot_sensor_simulator import TurbineSensor

class ArubaEdgeSimulator:
    """
    Simulates an Aruba Edge device that processes sensor data,
    detects gross anomalies, and sends alerts/triggers via actual HTTP calls.
    """
    def __init__(self):
        self.config = load_app_config('aruba_edge_simulator')
        if not self.config:
            print("FATAL ERROR: ArubaEdgeSimulator FAILED to load 'aruba_edge_simulator' configuration section. Cannot proceed.")
            raise ValueError("Failed to load 'aruba_edge_simulator' configuration section.")

        full_cfg_for_globals = get_full_config()
        company_name = full_cfg_for_globals.get('company_name_short', 'DefaultCo')
        
        template = self.config.get('device_id_template')
        num = self.config.get('default_device_id_num')

        if not template or num is None:
             error_msg = "Missing 'device_id_template' or 'default_device_id_num' in 'aruba_edge_simulator' config."
             print(f"FATAL ERROR: {error_msg}")
             raise KeyError(error_msg)
        self.device_id = template.format(company_name_short=company_name, id=num)
            
        self.thresholds = self.config.get('thresholds')
        if not self.thresholds:
            error_msg = "Missing 'thresholds' in 'aruba_edge_simulator' config."
            print(f"FATAL ERROR: {error_msg}")
            raise KeyError(error_msg)

        opsramp_cfg = self.config.get('opsramp', {})
        self.opsramp_metrics_endpoint = opsramp_cfg.get('metrics_endpoint', "FALLBACK_OPSRAMP_METRICS_ENDPOINT")
        self.opsramp_events_endpoint = opsramp_cfg.get('events_endpoint', "FALLBACK_OPSRAMP_EVENTS_ENDPOINT")
        
        self.pcai_trigger_endpoint = os.environ.get(
            'PCAI_AGENT_TRIGGER_ENDPOINT', 
            self.config.get('pcai_agent_trigger_endpoint')
        )

        if not self.pcai_trigger_endpoint:
            error_msg = "Missing 'pcai_agent_trigger_endpoint' in config and 'PCAI_AGENT_TRIGGER_ENDPOINT' environment variable not set."
            print(f"FATAL ERROR: {error_msg}")
            raise KeyError(error_msg)

        print(f"INFO: [{self.device_id}] Aruba Edge Simulator initialized.")
        print(f"INFO: [{self.device_id}] PCAI Trigger Endpoint (Actual HTTP): {self.pcai_trigger_endpoint}")


    def _make_actual_api_call(self, endpoint: str, payload: dict, method: str = "POST"):
        print(f"\n--- MAKING ACTUAL HTTP API CALL [{method}] ---")
        print(f"To Endpoint: {endpoint}")
        print(f"Payload:\n{json.dumps(payload, indent=2)}")
        
        response_summary = {"status": "error", "message": "Call not attempted or unknown error"}
        try:
            if method.upper() == "POST":
                response = requests.post(endpoint, json=payload, timeout=300) 
            elif method.upper() == "GET":
                response = requests.get(endpoint, params=payload, timeout=300)
            else:
                print(f"ERROR: Unsupported HTTP method '{method}' for API call.")
                response_summary = {"status": "error", "message": f"Unsupported HTTP method: {method}"}
                return response_summary
            response.raise_for_status() 
            
            print(f"SUCCESS: API Call to {endpoint} successful. Status: {response.status_code}")
            try:
                response_summary = {"status": "success", "response_data": response.json(), "status_code": response.status_code}
            except requests.exceptions.JSONDecodeError: 
                response_summary = {"status": "success", "response_data": response.text, "status_code": response.status_code}
        except requests.exceptions.ConnectionError as e:
            print(f"ERROR: API Call ConnectionError to {endpoint}: {e}")
            response_summary = {"status": "error", "message": f"Connection error to {endpoint}: {e}"}
        except requests.exceptions.Timeout as e:
            print(f"ERROR: API Call Timeout to {endpoint}: {e}")
            response_summary = {"status": "error", "message": f"Timeout error for {endpoint}: {e}"}
        except requests.exceptions.HTTPError as e:
            print(f"ERROR: API Call HTTPError to {endpoint}: {e.response.status_code} - {e.response.text[:200]}...")
            response_summary = {"status": "error", "message": f"HTTP error: {e.response.status_code}", "details": e.response.text[:500]}
        except requests.exceptions.RequestException as e:
            print(f"ERROR: API Call RequestException to {endpoint}: {e}")
            response_summary = {"status": "error", "message": f"General request error for {endpoint}: {e}"}
        finally:
            print(f"--- END ACTUAL HTTP API CALL (Status: {response_summary.get('status')}) ---")
        return response_summary

    def _send_metrics_to_opsramp(self, sensor_data: dict):
        metrics_payload = {
            "source_device_id": self.device_id,
            "asset_id": sensor_data["asset_id"], 
            "timestamp": sensor_data["timestamp"], 
            "metrics": {
                "temperature_c": sensor_data["temperature_c"],
                "temperature_increase_c": sensor_data.get("temperature_increase_c"),
                "vibration_overall_amplitude_g": sensor_data["vibration_overall_amplitude_g"],
                "vibration_dominant_frequency_hz": sensor_data["vibration_dominant_frequency_hz"],
                "acoustic_overall_db": sensor_data["acoustic_overall_db"],
                "acoustic_critical_band_db": sensor_data["acoustic_critical_band_db"],
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
        detected_anomalies = []
        if sensor_data["temperature_c"] > self.thresholds["temperature_critical_c"]:
            detected_anomalies.append({
                "type": "CriticalTemperature",
                "message": f"Temperature {sensor_data['temperature_c']}°C exceeds threshold of {self.thresholds['temperature_critical_c']}°C.",
                "value": sensor_data["temperature_c"], "threshold": self.thresholds["temperature_critical_c"]})
        if sensor_data.get("vibration_anomaly_signature_amp_g") is not None and \
           sensor_data["vibration_anomaly_signature_amp_g"] > self.thresholds["vibration_anomaly_amp_g"]:
            detected_anomalies.append({
                "type": "HighAmplitudeVibrationSignature",
                "message": (f"Vibration anomaly signature {sensor_data['vibration_anomaly_signature_amp_g']}g "
                            f"at {sensor_data['vibration_anomaly_signature_freq_hz']}Hz "
                            f"exceeds threshold of {self.thresholds['vibration_anomaly_amp_g']}g."),
                "anomaly_frequency_hz": sensor_data['vibration_anomaly_signature_freq_hz'],
                "anomaly_amplitude_g": sensor_data['vibration_anomaly_signature_amp_g'],
                "threshold_amp_g": self.thresholds['vibration_anomaly_amp_g']})
        if sensor_data["acoustic_critical_band_db"] > self.thresholds["acoustic_critical_band_db"]:
            detected_anomalies.append({
                "type": "AnomalousAcousticCriticalBand",
                "message": f"Acoustic critical band {sensor_data['acoustic_critical_band_db']}dB exceeds threshold of {self.thresholds['acoustic_critical_band_db']}dB.",
                "value_db": sensor_data["acoustic_critical_band_db"], "threshold_db": self.thresholds['acoustic_critical_band_db']})
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
        api_call_result = self._make_actual_api_call(self.pcai_trigger_endpoint, pcai_trigger_payload, method="POST")
        if api_call_result and api_call_result.get("status") == "success":
            print(f"INFO: [{self.device_id}] Successfully sent trigger to PCAI. Response status: {api_call_result.get('status_code')}")
        else:
            print(f"WARN: [{self.device_id}] Failed to send trigger to PCAI or received error. Details: {api_call_result}")

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

# --- NEW INDEFINITE SIMULATION LOGIC ---
if __name__ == "__main__":
    sensor_asset_id = "Default_Sensor_Asset_000_EdgeMain"
    sensor_data_interval = 2
    sensor_base_temp = 42.0

    try:
        full_cfg_main = get_full_config() 
        iot_sim_cfg_main = {}
        if full_cfg_main:
            iot_sim_cfg_main = full_cfg_main.get('iot_sensor_simulator', {})
            company_name_main = full_cfg_main.get('company_name_short', 'TestCo')
            
            asset_prefix_template_main = iot_sim_cfg_main.get('asset_id_prefix', "{company_name_short}_Turbine")
            asset_prefix_main = asset_prefix_template_main.format(company_name_short=company_name_main)
            asset_num_main = iot_sim_cfg_main.get('default_asset_number', 7)
            sensor_asset_id = f"{asset_prefix_main}_{asset_num_main:03d}"
            
            sensor_data_interval = iot_sim_cfg_main.get('data_interval_seconds', sensor_data_interval)
            sensor_base_temp = iot_sim_cfg_main.get('base_temp_c', sensor_base_temp)
            print(f"INFO: [EdgeSim __main__] Loaded IoT sensor settings using common_utils for {sensor_asset_id}.")
        else:
            print(f"WARN: [EdgeSim __main__] Full config not loaded by common_utils. Using default sensor settings.")

        edge_sim = ArubaEdgeSimulator() 
        sensor = TurbineSensor(asset_id=sensor_asset_id, base_temp_c_from_config=sensor_base_temp)

        print(f"\n--- Starting INDEFINITE Edge Simulation with IoT Sensor: {sensor.asset_id} ---")
        print(f"--- Edge will make ACTUAL HTTP calls to PCAI endpoint: {edge_sim.pcai_trigger_endpoint} ---")
        print(f"--- Data interval: {sensor_data_interval}s. Anomaly will toggle on/off. Press Ctrl+C to stop. ---")
        
        iteration_count = 0
        is_currently_anomalous = False
        # Define how long each period of normal/anomalous data should last
        NORMAL_CYCLES = 15
        ANOMALY_CYCLES = 20 # Run anomaly for a bit longer to ensure it's triggered/seen

        while True:
            cycle_in_period = iteration_count % (NORMAL_CYCLES + ANOMALY_CYCLES)

            # Check if we should switch state
            if cycle_in_period == 0 and is_currently_anomalous:
                print("\nDEMO OPERATOR ACTION: Reverting anomaly in sensor (end of period)...\n")
                sensor.set_anomaly_status(False)
                is_currently_anomalous = False
            elif cycle_in_period == NORMAL_CYCLES and not is_currently_anomalous:
                print("\nDEMO OPERATOR ACTION: Injecting anomaly into sensor (start of period)...\n")
                sensor.set_anomaly_status(True)
                is_currently_anomalous = True

            print(f"\n--- Cycle {iteration_count + 1} (Period Cycle: {cycle_in_period + 1}, Anomaly State: {is_currently_anomalous}) ---")
            
            current_sensor_data = sensor.generate_data()
            print(f"SENSOR ({sensor.asset_id}) generated: {json.dumps(current_sensor_data, indent=2)}")
            edge_sim.process_sensor_data(current_sensor_data)
            
            iteration_count += 1
            time.sleep(sensor_data_interval)

    except (ValueError, KeyError) as e_conf: 
        print(f"FATAL: Configuration error during ArubaEdgeSimulator setup: {e_conf}")
    except KeyboardInterrupt:
        print("\nINFO: Edge simulation test stopped by user.")
    except Exception as e_generic:
        print(f"An unexpected error occurred in EdgeSim __main__: {e_generic}")
        import traceback
        traceback.print_exc()