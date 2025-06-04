# data_simulators/iot_sensor_simulator.py

import time
import datetime
import random
import os # For path joining in __main__

class TurbineSensor:
    """
    Simulates an IoT sensor on a wind turbine, generating operational data.
    It can be toggled to produce normal or anomalous data streams.
    """
    def __init__(self, asset_id="Default_Turbine_000", base_temp_c_from_config=42.0):
        self.asset_id = asset_id
        self.anomaly_active = False
        
        # Baseline normal operating parameters
        self.base_temp_c = base_temp_c_from_config # Use config value
        self.base_vib_amplitude_g = 0.3  # g
        self.base_vib_frequency_hz = 60.0  # Hz (main operational frequency)
        self.base_acoustic_db = 70.0  # decibels
        self.base_acoustic_crit_band_db = 50.0 # decibels for a specific critical band

        # Anomaly characteristics (when active) - aligned with demo narrative
        self.anomaly_vib_target_freq_hz = 121.0 # Hz (e.g., gear mesh frequency, target for RAG)
        self.anomaly_vib_target_amp_g = 2.5   # g (amplitude of the anomaly frequency)
        self.anomaly_temp_max_increase_c = 6.0 # Max temperature increase during anomaly (target for RAG)
        self.anomaly_acoustic_crit_band_increase_db = 15.0 # dB increase
        self.anomaly_overall_acoustic_increase_db = 5.0 # dB increase

        # State for gradual changes during anomaly
        self.current_temp_increase_c = 0.0
        self.current_vib_anomaly_amp_g = 0.0 # Initialize to 0, will ramp up/down

    def set_anomaly_status(self, status: bool):
        """
        Activates or deactivates the anomaly generation.
        Resets anomaly progression when an anomaly is newly activated.
        """
        if status and not self.anomaly_active: # Transitioning to anomaly active
            print(f"INFO: [{self.asset_id} SENSOR] Anomaly INJECTED by operator.")
            self.current_temp_increase_c = 0.0 
            self.current_vib_anomaly_amp_g = 0.0 
        elif not status and self.anomaly_active: # Transitioning to normal
            print(f"INFO: [{self.asset_id} SENSOR] Anomaly REVERTED by operator.")
        
        self.anomaly_active = status

    def _get_gradual_value(self, current_val, target_val, step_fraction=0.25, noise_range=0.05):
        """Helper to simulate gradual change towards a target."""
        if abs(current_val - target_val) < 0.01:
            return target_val
        
        diff = target_val - current_val
        step_fraction = abs(step_fraction)
        change = diff * step_fraction 
        
        if abs(change) > 0.001 :
             change += (change * random.uniform(-noise_range, noise_range))
        
        new_val = current_val + change
        
        if diff > 0: 
            return min(new_val, target_val)
        else: 
            return max(new_val, target_val)

    def generate_data(self) -> dict:
        """
        Generates a single data point (dictionary) for the turbine sensor.
        """
        timestamp = datetime.datetime.utcnow().isoformat(timespec='milliseconds') + "Z"
        
        temp_c = self.base_temp_c + random.uniform(-0.5, 0.5)
        vib_amp_g = self.base_vib_amplitude_g + random.uniform(-0.05, 0.05)
        vib_freq_hz = self.base_vib_frequency_hz + random.uniform(-0.2, 0.2)
        acoustic_db = self.base_acoustic_db + random.uniform(-1.0, 1.0)
        acoustic_crit_band_db = self.base_acoustic_crit_band_db + random.uniform(-2.0, 2.0)

        anomaly_signature_vibration_freq_hz = None
        anomaly_signature_vibration_amp_g = None
        current_temp_increase_for_payload = self.current_temp_increase_c # Keep track for payload

        if self.anomaly_active:
            self.current_temp_increase_c = self._get_gradual_value(
                self.current_temp_increase_c, 
                self.anomaly_temp_max_increase_c,
                step_fraction=0.3 
            )
            temp_c = self.base_temp_c + self.current_temp_increase_c + random.uniform(-0.2, 0.2)
            current_temp_increase_for_payload = self.current_temp_increase_c

            anomaly_signature_vibration_freq_hz = self.anomaly_vib_target_freq_hz + random.uniform(-0.5, 0.5)
            
            self.current_vib_anomaly_amp_g = self._get_gradual_value(
                self.current_vib_anomaly_amp_g,
                self.anomaly_vib_target_amp_g,
                step_fraction=0.35
            )
            anomaly_signature_vibration_amp_g = self.current_vib_anomaly_amp_g
            vib_amp_g += (self.current_vib_anomaly_amp_g * 0.1) 

            severity_factor = min(self.current_vib_anomaly_amp_g / self.anomaly_vib_target_amp_g, 1.0) if self.anomaly_vib_target_amp_g > 0 else 0
            acoustic_crit_band_db = self.base_acoustic_crit_band_db + \
                                    self.anomaly_acoustic_crit_band_increase_db * severity_factor + \
                                    random.uniform(-1.5, 1.5)
            acoustic_db = self.base_acoustic_db + \
                          self.anomaly_overall_acoustic_increase_db * severity_factor + \
                          random.uniform(-0.5, 0.5)
        else:
            self.current_vib_anomaly_amp_g = self._get_gradual_value(
                self.current_vib_anomaly_amp_g, 0.0, step_fraction=0.2
            )
            if self.current_vib_anomaly_amp_g > 0.01:
                anomaly_signature_vibration_freq_hz = self.anomaly_vib_target_freq_hz + random.uniform(-0.5, 0.5)
                anomaly_signature_vibration_amp_g = self.current_vib_anomaly_amp_g
            else:
                 anomaly_signature_vibration_amp_g = None

            self.current_temp_increase_c = self._get_gradual_value(
                self.current_temp_increase_c, 0.0, step_fraction=0.2
            )
            temp_c = self.base_temp_c + self.current_temp_increase_c + random.uniform(-0.5, 0.5)
            current_temp_increase_for_payload = self.current_temp_increase_c

        return {
            "timestamp": timestamp,
            "asset_id": self.asset_id,
            "temperature_c": round(temp_c, 2),
            "temperature_increase_c": round(current_temp_increase_for_payload, 2), # Crucial for RAG
            "vibration_overall_amplitude_g": round(vib_amp_g, 3),
            "vibration_dominant_frequency_hz": round(vib_freq_hz, 2),
            "vibration_anomaly_signature_freq_hz": round(anomaly_signature_vibration_freq_hz, 2) if anomaly_signature_vibration_freq_hz is not None else None,
            "vibration_anomaly_signature_amp_g": round(anomaly_signature_vibration_amp_g, 3) if anomaly_signature_vibration_amp_g is not None else None,
            "acoustic_overall_db": round(acoustic_db, 1),
            "acoustic_critical_band_db": round(acoustic_crit_band_db, 1),
            "is_anomaly_induced": self.anomaly_active 
        }

if __name__ == "__main__":
    # --- Default values for standalone execution ---
    DEFAULT_ASSET_ID = "Default_Turbine_007"
    DEFAULT_DATA_INTERVAL = 2
    DEFAULT_BASE_TEMP = 42.0

    # --- Attempt to load from central config for consistency ---
    # This allows running the sensor simulator standalone while adhering to centralized config
    final_asset_id = DEFAULT_ASSET_ID
    final_data_interval = DEFAULT_DATA_INTERVAL
    final_base_temp = DEFAULT_BASE_TEMP
    
    try:
        import yaml # Keep PyYAML for this optional config loading
        
        # Construct path to config relative to this script's location if possible,
        # assuming script is in data_simulators/ and config is in project_root/config/
        script_dir = os.path.dirname(__file__)
        config_file_path = os.path.join(script_dir, "..", "config", "demo_config.yaml")

        if not os.path.exists(config_file_path):
            # Fallback if running from project root directly (e.g. python data_simulators/iot_sensor_simulator.py)
            config_file_path = os.path.join("config", "demo_config.yaml")

        if os.path.exists(config_file_path):
            with open(config_file_path, 'r') as f:
                full_config = yaml.safe_load(f)
            
            company_name = full_config.get('company_name_short', 'DefaultCo')
            iot_sim_config = full_config.get('iot_sensor_simulator', {})
            
            asset_prefix_template = iot_sim_config.get('asset_id_prefix', "{company_name_short}_Turbine")
            asset_prefix = asset_prefix_template.format(company_name_short=company_name)
            asset_num = iot_sim_config.get('default_asset_number', 7)
            final_asset_id = f"{asset_prefix}_{asset_num:03d}"
            
            final_data_interval = iot_sim_config.get('data_interval_seconds', DEFAULT_DATA_INTERVAL)
            final_base_temp = iot_sim_config.get('base_temp_c', DEFAULT_BASE_TEMP)
            
            print(f"INFO: [{final_asset_id} SENSOR] Loaded settings from {config_file_path}")
        else:
            print(f"WARN: Config file not found at expected paths. Using defaults for sensor.")
            
    except ImportError:
        print(f"WARN: PyYAML not found. Cannot load from config file. Using defaults for sensor.")
    except Exception as e:
        print(f"WARN: Could not load from config file ({e}). Using defaults for sensor.")
    # --- End attempt to load from config ---

    sensor = TurbineSensor(asset_id=final_asset_id, base_temp_c_from_config=final_base_temp)
    
    print(f"Starting IoT Sensor Simulator for {sensor.asset_id}...")
    print(f"Base Temperature: {sensor.base_temp_c}°C")
    print(f"Data generation interval: {final_data_interval}s")
    print("Will run for 20 cycles: 5 normal, 10 anomalous, 5 normal. Press Ctrl+C to stop.")
    print("-" * 30)

    for i in range(20):
        print(f"\nCycle {i+1}:")

        if i == 5: 
            sensor.set_anomaly_status(True)
        elif i == 15: 
            sensor.set_anomaly_status(False)
            
        data_packet = sensor.generate_data()
        
        print(f"  Timestamp: {data_packet['timestamp']}")
        print(f"  Asset ID: {data_packet['asset_id']}")
        print(f"  Temperature: {data_packet['temperature_c']} °C (Increase: {data_packet['temperature_increase_c']} °C)")
        print(f"  Vibration (Overall): {data_packet['vibration_overall_amplitude_g']}g @ {data_packet['vibration_dominant_frequency_hz']}Hz")
        if data_packet['vibration_anomaly_signature_freq_hz'] is not None and \
           data_packet['vibration_anomaly_signature_amp_g'] is not None :
            print(f"  Vibration (Anomaly Signature): {data_packet['vibration_anomaly_signature_amp_g']}g @ {data_packet['vibration_anomaly_signature_freq_hz']}Hz")
        print(f"  Acoustic (Overall): {data_packet['acoustic_overall_db']} dB")
        print(f"  Acoustic (Critical Band): {data_packet['acoustic_critical_band_db']} dB")
        print(f"  Anomaly State (Sensor): {data_packet['is_anomaly_induced']}")
        
        time.sleep(final_data_interval)

    print("-" * 30)
    print("IoT Sensor Simulator finished its run.")