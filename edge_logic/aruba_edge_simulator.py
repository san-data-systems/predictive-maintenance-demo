# edge_logic/aruba_edge_simulator.py

import json
import time
import os # For __main__ config path

# Import utilities
from utilities import get_utc_timestamp, load_app_config, get_full_config

from data_simulators.iot_sensor_simulator import TurbineSensor # Keep this import

class ArubaEdgeSimulator:
    def __init__(self): # Removed config_path, utility will find it
        self.config = load_app_config('aruba_edge_simulator')
        if not self.config:
            print("FATAL ERROR: ArubaEdgeSimulator FAILED to load 'aruba_edge_simulator' configuration section. Cannot proceed.")
            raise ValueError("Failed to load 'aruba_edge_simulator' configuration section.")

        full_cfg_for_globals = get_full_config()
        company_name = full_cfg_for_globals.get('company_name_short', 'DefaultCo')
        
        template = self.config.get('device_id_template')
        num = self.config.get('default_device_id_num')
        if not template or num is None:
             raise KeyError("Missing 'device_id_template' or 'default_device_id_num' in Aruba Edge Simulator config.")
        self.device_id = template.format(company_name_short=company_name, id=num)
            
        self.thresholds = self.config.get('thresholds')
        if not self.thresholds:
            raise KeyError("Missing 'thresholds' in Aruba Edge Simulator config.")

        opsramp_cfg = self.config.get('opsramp', {})
        self.opsramp_metrics_endpoint = opsramp_cfg.get('metrics_endpoint', "FALLBACK_OPSRAMP_METRICS_ENDPOINT")
        self.opsramp_events_endpoint = opsramp_cfg.get('events_endpoint', "FALLBACK_OPSRAMP_EVENTS_ENDPOINT")
        
        self.pcai_trigger_endpoint = self.config.get('pcai_agent_trigger_endpoint')
        if not self.pcai_trigger_endpoint:
            raise KeyError("Missing 'pcai_agent_trigger_endpoint' in Aruba Edge Simulator config.")

        print(f"INFO: [{self.device_id}] Aruba Edge Simulator initialized using common_utils.")
        print(f"INFO: [{self.device_id}] Thresholds: {self.thresholds}")
        # ... (other print statements for endpoints if desired) ...

    def _simulate_api_call(self, endpoint: str, payload: dict, method: str = "POST"):
        print(f"\n--- SIMULATING API CALL [{method}] ---")
        print(f"To Endpoint: {endpoint}")
        print(f"Payload:\n{json.dumps(payload, indent=2)}")
        print(f"--- END SIMULATED API CALL ---")
        return {"status": "simulated_success", "message_id": "sim_" + get_utc_timestamp()}


    def _send_metrics_to_opsramp(self, sensor_data: dict):
        metrics_payload = {
            "source_device_id": self.device_id,
            "asset_id": sensor_data["asset_id"],
            "timestamp": sensor_data["timestamp"], # Use sensor's original timestamp for metrics
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
        self._simulate_api_call(self.opsramp_metrics_endpoint, metrics_payload)


    def _detect_gross_anomalies(self, sensor_data: dict) -> list:
        detected_anomalies = []
        if sensor_data["temperature_c"] > self.thresholds["temperature_critical_c"]:
            detected_anomalies.append({
                "type": "CriticalTemperature",
                "message": f"Temperature {sensor_data['temperature_c']}°C exceeds threshold.",
                "value": sensor_data["temperature_c"], "threshold": self.thresholds["temperature_critical_c"]})
        if sensor_data.get("vibration_anomaly_signature_amp_g") is not None and \
           sensor_data["vibration_anomaly_signature_amp_g"] > self.thresholds["vibration_anomaly_amp_g"]:
            detected_anomalies.append({
                "type": "HighAmplitudeVibrationSignature",
                "message": f"Vibration anomaly signature {sensor_data['vibration_anomaly_signature_amp_g']}g @ {sensor_data['vibration_anomaly_signature_freq_hz']}Hz exceeds threshold.",
                "anomaly_frequency_hz": sensor_data['vibration_anomaly_signature_freq_hz'],
                "anomaly_amplitude_g": sensor_data['vibration_anomaly_signature_amp_g'],
                "threshold_amp_g": self.thresholds['vibration_anomaly_amp_g']})
        if sensor_data["acoustic_critical_band_db"] > self.thresholds["acoustic_critical_band_db"]:
            detected_anomalies.append({
                "type": "AnomalousAcousticCriticalBand",
                "message": f"Acoustic critical band {sensor_data['acoustic_critical_band_db']}dB exceeds threshold.",
                "value_db": sensor_data["acoustic_critical_band_db"], "threshold_db": self.thresholds['acoustic_critical_band_db']})
        return detected_anomalies

    def _send_event_to_opsramp(self, sensor_data: dict, anomaly_details: dict):
        event_title = f"Anomalous {anomaly_details['type']} on {sensor_data['asset_id']}"
        if anomaly_details['type'] == "HighAmplitudeVibrationSignature": 
             event_title = f"Anomalous vibration pattern detected on {sensor_data['asset_id']}"
        event_payload = {
            "source_id": self.device_id, "resource_id": sensor_data["asset_id"], 
            "timestamp": get_utc_timestamp(), # New timestamp for the event itself
            "severity": "CRITICAL", "title": event_title,
            "description": f"Edge logic: {anomaly_details['message']} Escalating to PCAI.",
            "details": {"triggering_anomaly": anomaly_details, "sensor_readings": sensor_data}
        }
        print(f"ALERT: [{self.device_id}] Sending CRITICAL EVENT to OpsRamp: {event_payload['title']}")
        self._simulate_api_call(self.opsramp_events_endpoint, event_payload)

    def _send_trigger_to_pcai(self, sensor_data: dict, all_detected_anomalies: list):
        pcai_trigger_payload = {
            "source_component": self.device_id, "asset_id": sensor_data["asset_id"],
            "trigger_timestamp": get_utc_timestamp(), # New timestamp for the trigger
            "edge_detected_anomalies": all_detected_anomalies, 
            "full_sensor_data_at_trigger": sensor_data 
        }
        print(f"INFO: [{self.device_id}] Sending Anomaly Trigger to PCAI for {sensor_data['asset_id']}")
        self._simulate_api_call(self.pcai_trigger_endpoint, pcai_trigger_payload)

    def process_sensor_data(self, sensor_data: dict):
        print(f"\nINFO: [{self.device_id}] Processing data for {sensor_data['asset_id']} at {sensor_data['timestamp']}")
        self._send_metrics_to_opsramp(sensor_data)
        anomalies = self._detect_gross_anomalies(sensor_data)
        if anomalies:
            print(f"WARN: [{self.device_id}] Gross anomalies DETECTED for {sensor_data['asset_id']}:")
            for anomaly in anomalies: print(f"  - Type: {anomaly['type']}, Message: {anomaly['message']}")
            self._send_event_to_opsramp(sensor_data, anomalies[0])
            self._send_trigger_to_pcai(sensor_data, anomalies)
        else:
            print(f"INFO: [{self.device_id}] Data for {sensor_data['asset_id']} within normal edge parameters.")

if __name__ == "__main__":
    sensor_asset_id = "Default_Sensor_Asset_000_EdgeMain"
    sensor_data_interval = 2
    sensor_base_temp = 42.0

    try:
        # Load sensor configuration using utilities
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

        # Instantiate the edge simulator (it will load its own config via utility)
        edge_sim = ArubaEdgeSimulator() 
        sensor = TurbineSensor(asset_id=sensor_asset_id, base_temp_c_from_config=sensor_base_temp)

        print(f"\n--- Starting Edge Simulation Test with IoT Sensor: {sensor.asset_id} ---")
        print(f"--- Data interval: {sensor_data_interval}s. Ctrl+C to stop. ---")
        print("--- Simulating: 5 normal, 10 anomalous, 5 normal. ---")

        for i in range(20): 
            print(f"\n--- Cycle {i+1}/20 ---")
            if i == 5: sensor.set_anomaly_status(True)
            elif i == 15: sensor.set_anomaly_status(False)
            current_sensor_data = sensor.generate_data()
            print(f"SENSOR ({sensor.asset_id}) generated: {json.dumps(current_sensor_data, indent=2)}")
            edge_sim.process_sensor_data(current_sensor_data)
            time.sleep(sensor_data_interval)

    except (ValueError, KeyError) as e_conf: # Catch errors from config loading in ArubaEdgeSimulator init
        print(f"FATAL: Configuration error during ArubaEdgeSimulator setup: {e_conf}")
    except KeyboardInterrupt:
        print("\nINFO: Edge simulation test stopped by user.")
    except Exception as e_generic:
        print(f"An unexpected error occurred in EdgeSim __main__: {e_generic}")
        import traceback
        traceback.print_exc()