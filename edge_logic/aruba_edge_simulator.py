import yaml
import json
import datetime
import time
# To use the sensor simulator for testing, we'll import it.
# Make sure your project structure allows this import.
# You might need to adjust PYTHONPATH or run from the project root.
from data_simulators.iot_sensor_simulator import TurbineSensor

class ArubaEdgeSimulator:
    """
    Simulates an Aruba Edge device that processes sensor data,
    detects gross anomalies, and sends alerts/triggers.
    """
    def __init__(self, config_path="config/demo_config.yaml"):
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)['aruba_edge_simulator']
        except FileNotFoundError:
            print(f"ERROR: Configuration file not found at {config_path}")
            raise
        except KeyError:
            print(f"ERROR: 'aruba_edge_simulator' section not found in config.")
            raise
            
        self.device_id = self.config['device_id']
        self.thresholds = self.config['thresholds']
        self.opsramp_metrics_endpoint = self.config['opsramp_metrics_endpoint']
        self.opsramp_events_endpoint = self.config['opsramp_events_endpoint']
        self.pcai_trigger_endpoint = self.config['pcai_agent_trigger_endpoint']

        print(f"INFO: [{self.device_id}] Aruba Edge Simulator initialized.")
        print(f"INFO: [{self.device_id}] Thresholds: {self.thresholds}")

    def _simulate_api_call(self, endpoint: str, payload: dict, method: str = "POST"):
        """
        Simulates making an API call. In a real scenario, this would use 'requests'.
        """
        print(f"SIMULATING API CALL [{method}] to: {endpoint}")
        print(f"Payload:\n{json.dumps(payload, indent=2)}")
        # In a real implementation:
        # try:
        #     if method.upper() == "POST":
        #         response = requests.post(endpoint, json=payload, timeout=5)
        #     elif method.upper() == "GET":
        #         response = requests.get(endpoint, params=payload, timeout=5)
        #     response.raise_for_status() # Raise an exception for HTTP errors
        #     print(f"API Call Successful: {response.status_code}")
        #     return response.json()
        # except requests.exceptions.RequestException as e:
        #     print(f"API Call Failed: {e}")
        #     return None
        return {"status": "simulated_success", "message_id": "sim_" + str(time.time_ns())}


    def _send_metrics_to_opsramp(self, sensor_data: dict):
        """
        Simulates sending key metrics from sensor_data to OpsRamp.
        """
        metrics_payload = {
            "source_device_id": self.device_id,
            "asset_id": sensor_data["asset_id"],
            "timestamp": sensor_data["timestamp"],
            "metrics": {
                "temperature_c": sensor_data["temperature_c"],
                "vibration_overall_amplitude_g": sensor_data["vibration_overall_amplitude_g"],
                "vibration_dominant_frequency_hz": sensor_data["vibration_dominant_frequency_hz"],
                "acoustic_overall_db": sensor_data["acoustic_overall_db"],
                "acoustic_critical_band_db": sensor_data["acoustic_critical_band_db"],
            }
        }
        if sensor_data.get("vibration_anomaly_signature_freq_hz") is not None:
            metrics_payload["metrics"]["vibration_anomaly_signature_freq_hz"] = sensor_data["vibration_anomaly_signature_freq_hz"]
            metrics_payload["metrics"]["vibration_anomaly_signature_amp_g"] = sensor_data["vibration_anomaly_signature_amp_g"]

        print(f"INFO: [{self.device_id}] Preparing to send metrics to OpsRamp for {sensor_data['asset_id']}.")
        self._simulate_api_call(self.opsramp_metrics_endpoint, metrics_payload)


    def _detect_gross_anomalies(self, sensor_data: dict) -> list:
        """
        Performs basic filtering and detects gross anomalies based on predefined thresholds.
        Returns a list of detected anomaly details.
        """
        detected_anomalies = []

        # Temperature check
        if sensor_data["temperature_c"] > self.thresholds["temperature_critical_c"]:
            detected_anomalies.append({
                "type": "CriticalTemperature",
                "message": f"Temperature {sensor_data['temperature_c']}°C exceeds threshold of {self.thresholds['temperature_critical_c']}°C.",
                "value": sensor_data["temperature_c"],
                "threshold": self.thresholds["temperature_critical_c"]
            })

        # Vibration anomaly signature check (only if signature is present and its amplitude is high)
        if sensor_data.get("vibration_anomaly_signature_amp_g") is not None and \
           sensor_data["vibration_anomaly_signature_amp_g"] > self.thresholds["vibration_anomaly_amp_g"]:
            detected_anomalies.append({
                "type": "HighAmplitudeVibrationSignature",
                "message": (f"Vibration anomaly signature amplitude {sensor_data['vibration_anomaly_signature_amp_g']}g "
                            f"at {sensor_data['vibration_anomaly_signature_freq_hz']}Hz "
                            f"exceeds threshold of {self.thresholds['vibration_anomaly_amp_g']}g."),
                "anomaly_frequency_hz": sensor_data['vibration_anomaly_signature_freq_hz'],
                "anomaly_amplitude_g": sensor_data['vibration_anomaly_signature_amp_g'],
                "threshold_amp_g": self.thresholds['vibration_anomaly_amp_g']
            })
        
        # Acoustic critical band check
        if sensor_data["acoustic_critical_band_db"] > self.thresholds["acoustic_critical_band_db"]:
            detected_anomalies.append({
                "type": "AnomalousAcousticCriticalBand",
                "message": f"Acoustic critical band {sensor_data['acoustic_critical_band_db']}dB exceeds threshold of {self.thresholds['acoustic_critical_band_db']}dB.",
                "value_db": sensor_data["acoustic_critical_band_db"],
                "threshold_db": self.thresholds['acoustic_critical_band_db']
            })
            
        return detected_anomalies


    def _send_event_to_opsramp(self, sensor_data: dict, anomaly_details: dict):
        """
        Simulates sending an "Edge Detected Anomaly" event to OpsRamp.
        anomaly_details is the first detected anomaly for the event title.
        """
        event_title = f"Anomalous {anomaly_details['type']} detected on {sensor_data['asset_id']}"
        if anomaly_details['type'] == "HighAmplitudeVibrationSignature": # Specific title from demo plan
             event_title = f"Anomalous vibration pattern detected on {sensor_data['asset_id']}"


        event_payload = {
            "source_id": self.device_id, # As per demo plan: "Edge Device TX-4B7"
            "resource_id": sensor_data["asset_id"], # Or a more specific OpsRamp resource ID
            "timestamp": datetime.datetime.utcnow().isoformat(timespec='milliseconds') + "Z",
            "severity": "CRITICAL", # Could be dynamic based on rules
            "title": event_title,
            "description": f"Edge logic detected a critical condition. Details: {anomaly_details['message']} Escalating to PCAI.",
            "details": { # Additional structured details
                "triggering_anomaly": anomaly_details,
                "all_sensor_readings_at_event": sensor_data
            }
        }
        print(f"ALERT: [{self.device_id}] Sending CRITICAL EVENT to OpsRamp: {event_payload['title']}")
        self._simulate_api_call(self.opsramp_events_endpoint, event_payload)

    def _send_trigger_to_pcai(self, sensor_data: dict, all_detected_anomalies: list):
        """
        Simulates sending an "Anomaly Trigger" with key data to the Agentic AI on PCAI.
        """
        pcai_trigger_payload = {
            "source_component": self.device_id,
            "asset_id": sensor_data["asset_id"],
            "trigger_timestamp": datetime.datetime.utcnow().isoformat(timespec='milliseconds') + "Z",
            "edge_detected_anomalies": all_detected_anomalies, # List of all anomalies detected by edge
            "full_sensor_data_at_trigger": sensor_data # The complete data packet that led to trigger
        }
        print(f"INFO: [{self.device_id}] Sending Anomaly Trigger to PCAI for {sensor_data['asset_id']}")
        self._simulate_api_call(self.pcai_trigger_endpoint, pcai_trigger_payload)


    def process_sensor_data(self, sensor_data: dict):
        """
        Main processing method for incoming sensor data.
        """
        print(f"\nINFO: [{self.device_id}] Processing data for {sensor_data['asset_id']} at {sensor_data['timestamp']}")
        
        # 1. Always send (or simulate sending) metrics to OpsRamp
        self._send_metrics_to_opsramp(sensor_data)

        # 2. Perform gross anomaly detection
        anomalies = self._detect_gross_anomalies(sensor_data)

        if anomalies:
            print(f"WARN: [{self.device_id}] Gross anomalies DETECTED for {sensor_data['asset_id']}:")
            for anomaly in anomalies:
                print(f"  - Type: {anomaly['type']}, Message: {anomaly['message']}")
            
            # 3. If anomalies, send event to OpsRamp (using the first detected anomaly for the main event)
            self._send_event_to_opsramp(sensor_data, anomalies[0])
            
            # 4. If anomalies, send trigger to PCAI Agent
            self._send_trigger_to_pcai(sensor_data, anomalies)
        else:
            print(f"INFO: [{self.device_id}] Data for {sensor_data['asset_id']} within normal edge parameters.")


if __name__ == "__main__":
    # Ensure config path is relative to the project root if running this script directly
    # For VS Code "Run Python File", it typically runs from project root.
    # If running from edge_logic/, path might need to be "../config/demo_config.yaml"
    config_file_path = "config/demo_config.yaml" 
    
    try:
        edge_sim = ArubaEdgeSimulator(config_path=config_file_path)
        
        # Use the TurbineSensor to generate data for testing
        # Load sensor config from the same file
        with open(config_file_path, 'r') as f:
            sensor_config = yaml.safe_load(f)['iot_sensor_simulator']

        sensor = TurbineSensor(asset_id=sensor_config.get("asset_id", "Turbine_007_Test"))
        data_interval = sensor_config.get("data_interval_seconds", 2)

        print("\n--- Starting Edge Simulation Test with IoT Sensor Data ---")
        print(f"--- Data will be generated every {data_interval} seconds. Press Ctrl+C to stop. ---")
        print("--- Simulating: 5 normal cycles, then 10 anomalous, then 5 normal. ---")

        for i in range(20): # Simulate 20 data points
            print(f"\n--- Cycle {i+1}/20 ---")
            if i == 5: # Inject anomaly
                print("\nDEMO OPERATOR ACTION: Injecting anomaly into sensor...\n")
                sensor.set_anomaly_status(True)
            elif i == 15: # Revert anomaly
                print("\nDEMO OPERATOR ACTION: Reverting anomaly in sensor...\n")
                sensor.set_anomaly_status(False)

            current_sensor_data = sensor.generate_data()
            print(f"SENSOR generated: {json.dumps(current_sensor_data, indent=2)}")
            edge_sim.process_sensor_data(current_sensor_data)
            time.sleep(data_interval)

    except FileNotFoundError:
        print("Ensure 'config/demo_config.yaml' exists and paths are correct.")
    except KeyError as e:
        print(f"Configuration error: Missing key {e} in 'config/demo_config.yaml'.")
    except KeyboardInterrupt:
        print("\nINFO: Edge simulation test stopped by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")