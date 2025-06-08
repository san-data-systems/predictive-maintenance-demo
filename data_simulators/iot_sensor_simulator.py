# data_simulators/iot_sensor_simulator.py

import time
import datetime
import random
import json
import os
import paho.mqtt.client as mqtt
import logging

from utilities import get_utc_timestamp, get_full_config

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TurbineSensor:
    # ... (This class content does not need to change) ...
    # ... (Leaving it out for brevity, just copy the whole file) ...
    def __init__(self, asset_id="Default_Turbine_000", base_temp_c_from_config=42.0):
        self.asset_id = asset_id
        self.anomaly_active = False
        self.base_temp_c = base_temp_c_from_config
        self.base_vib_amplitude_g = 0.3
        self.base_vib_frequency_hz = 60.0
        self.base_acoustic_db = 70.0
        self.base_acoustic_crit_band_db = 50.0
        self.anomaly_vib_target_freq_hz = 121.0
        self.anomaly_vib_target_amp_g = 2.5
        self.anomaly_temp_max_increase_c = 6.0
        self.anomaly_acoustic_crit_band_increase_db = 15.0
        self.anomaly_overall_acoustic_increase_db = 5.0
        self.current_temp_increase_c = 0.0
        self.current_vib_anomaly_amp_g = 0.0
        logging.info(f"[{self.asset_id} SENSOR] Initialized. Base Temp: {self.base_temp_c}°C")

    def set_anomaly_status(self, status: bool):
        if status and not self.anomaly_active:
            logging.info(f"[{self.asset_id} SENSOR] Anomaly INJECTED by operator.")
            self.current_temp_increase_c = 0.0 
            self.current_vib_anomaly_amp_g = 0.0 
        elif not status and self.anomaly_active:
            logging.info(f"[{self.asset_id} SENSOR] Anomaly REVERTED by operator.")
        self.anomaly_active = status

    def _get_gradual_value(self, current_val, target_val, step_fraction=0.25, noise_range=0.05):
        if abs(current_val - target_val) < 0.01: return target_val
        diff = target_val - current_val
        step_fraction = abs(step_fraction)
        change = diff * step_fraction 
        if abs(change) > 0.001: change += (change * random.uniform(-noise_range, noise_range))
        new_val = current_val + change
        return min(new_val, target_val) if diff > 0 else max(new_val, target_val)

    def generate_data(self) -> dict:
        timestamp = get_utc_timestamp()
        temp_c = self.base_temp_c + random.uniform(-0.5, 0.5)
        vib_amp_g = self.base_vib_amplitude_g + random.uniform(-0.05, 0.05)
        vib_freq_hz = self.base_vib_frequency_hz + random.uniform(-0.2, 0.2)
        acoustic_db = self.base_acoustic_db + random.uniform(-1.0, 1.0)
        acoustic_crit_band_db = self.base_acoustic_crit_band_db + random.uniform(-2.0, 2.0)
        anomaly_signature_vibration_freq_hz = None
        anomaly_signature_vibration_amp_g = None
        current_temp_increase_for_payload = self.current_temp_increase_c
        if self.anomaly_active:
            self.current_temp_increase_c = self._get_gradual_value(self.current_temp_increase_c, self.anomaly_temp_max_increase_c, step_fraction=0.3)
            temp_c = self.base_temp_c + self.current_temp_increase_c + random.uniform(-0.2, 0.2)
            current_temp_increase_for_payload = self.current_temp_increase_c
            anomaly_signature_vibration_freq_hz = self.anomaly_vib_target_freq_hz + random.uniform(-0.5, 0.5)
            self.current_vib_anomaly_amp_g = self._get_gradual_value(self.current_vib_anomaly_amp_g, self.anomaly_vib_target_amp_g, step_fraction=0.35)
            anomaly_signature_vibration_amp_g = self.current_vib_anomaly_amp_g
            vib_amp_g += (self.current_vib_anomaly_amp_g * 0.1)
            severity_factor = min(self.current_vib_anomaly_amp_g / self.anomaly_vib_target_amp_g, 1.0) if self.anomaly_vib_target_amp_g > 0 else 0
            acoustic_crit_band_db = self.base_acoustic_crit_band_db + self.anomaly_acoustic_crit_band_increase_db * severity_factor + random.uniform(-1.5, 1.5)
            acoustic_db = self.base_acoustic_db + self.anomaly_overall_acoustic_increase_db * severity_factor + random.uniform(-0.5, 0.5)
        else:
            self.current_vib_anomaly_amp_g = self._get_gradual_value(self.current_vib_anomaly_amp_g, 0.0, step_fraction=0.2)
            if self.current_vib_anomaly_amp_g > 0.01:
                anomaly_signature_vibration_freq_hz = self.anomaly_vib_target_freq_hz + random.uniform(-0.5, 0.5)
                anomaly_signature_vibration_amp_g = self.current_vib_anomaly_amp_g
            else:
                 anomaly_signature_vibration_amp_g = None
            self.current_temp_increase_c = self._get_gradual_value(self.current_temp_increase_c, 0.0, step_fraction=0.2)
            temp_c = self.base_temp_c + self.current_temp_increase_c + random.uniform(-0.5, 0.5)
            current_temp_increase_for_payload = self.current_temp_increase_c
        
        # Prepare a clean, flat dictionary for telemetry
        telemetry_data = {
            "temperature_c": round(temp_c, 2), 
            "temperature_increase_c": round(current_temp_increase_for_payload, 2), 
            "vibration_overall_amplitude_g": round(vib_amp_g, 3), 
            "vibration_dominant_frequency_hz": round(vib_freq_hz, 2),
            "acoustic_overall_db": round(acoustic_db, 1), 
            "acoustic_critical_band_db": round(acoustic_crit_band_db, 1),
            "is_anomaly_induced": self.anomaly_active
        }
        if anomaly_signature_vibration_amp_g is not None:
             telemetry_data["vibration_anomaly_signature_amp_g"] = round(anomaly_signature_vibration_amp_g, 3)
             telemetry_data["vibration_anomaly_signature_freq_hz"] = round(anomaly_signature_vibration_freq_hz, 2)
        
        # Full packet for internal use (edge logic)
        internal_data_packet = telemetry_data.copy()
        internal_data_packet["timestamp"] = timestamp
        internal_data_packet["asset_id"] = self.asset_id
        
        return internal_data_packet, telemetry_data


if __name__ == "__main__":
    
    config = get_full_config()
    iot_sim_config = config.get('iot_sensor_simulator', {})
    mqtt_config = config.get('mqtt', {})
    thingsboard_config = config.get('thingsboard', {})
    company_name = config.get('company_name_short', 'TestCo')
    
    asset_prefix_template = iot_sim_config.get('asset_id_prefix', "{company_name_short}_Turbine")
    asset_prefix = asset_prefix_template.format(company_name_short=company_name)
    asset_num = iot_sim_config.get('default_asset_number', 7)
    sensor_asset_id = f"{asset_prefix}_{asset_num:03d}"
    sensor_data_interval = iot_sim_config.get('data_interval_seconds', 2)
    sensor_base_temp = iot_sim_config.get('base_temp_c', 42.0)
    
    # Internal MQTT Broker Config
    internal_broker_hostname = os.environ.get("MQTT_BROKER_HOSTNAME", mqtt_config.get('broker_hostname', 'localhost'))
    internal_broker_port = int(os.environ.get("MQTT_BROKER_PORT", mqtt_config.get('broker_port', 1883)))
    internal_topic = mqtt_config.get('sensor_topic', 'hpe/demo/default/sensors')
    
    # ThingsBoard MQTT Config
    tb_host = thingsboard_config.get('host', 'localhost')
    tb_port = thingsboard_config.get('port', 1883) # <<< THIS LINE IS NOW CORRECTED
    tb_access_token = thingsboard_config.get('device_access_token')
    tb_topic = "v1/devices/me/telemetry"

    sensor = TurbineSensor(asset_id=sensor_asset_id, base_temp_c_from_config=sensor_base_temp)

    # --- Client for Internal MQTT Broker ---
    is_internal_connected = False
    def on_internal_connect(client, userdata, flags, reason_code, properties):
        global is_internal_connected
        if reason_code.is_failure:
            logging.error(f"INTERNAL MQTT | Failed to connect: {reason_code}")
            is_internal_connected = False
        else:
            logging.info("INTERNAL MQTT | Successfully connected.")
            is_internal_connected = True

    def on_internal_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        global is_internal_connected
        is_internal_connected = False
        logging.warning(f"INTERNAL MQTT | Unexpectedly disconnected: {reason_code}")

    internal_mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"iot-sensor-{sensor_asset_id}-internal")
    internal_mqtt_client.on_connect = on_internal_connect
    internal_mqtt_client.on_disconnect = on_internal_disconnect

    # --- Client for ThingsBoard MQTT ---
    is_tb_connected = False
    def on_tb_connect(client, userdata, flags, reason_code, properties):
        global is_tb_connected
        if reason_code.is_failure:
            logging.error(f"THINGSBOARD MQTT | Failed to connect: {reason_code}. Check host and access token.")
            is_tb_connected = False
        else:
            logging.info("THINGSBOARD MQTT | Successfully connected.")
            is_tb_connected = True

    def on_tb_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        global is_tb_connected
        is_tb_connected = False
        logging.warning(f"THINGSBOARD MQTT | Unexpectedly disconnected: {reason_code}")
    
    thingsboard_mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"iot-sensor-{sensor_asset_id}-tb")
    if "YOUR_TURBINE_DEVICE_ACCESS_TOKEN" in tb_access_token or not tb_access_token:
        logging.warning("THINGSBOARD MQTT | Access token is not set. ThingsBoard integration will be disabled.")
    else:
        thingsboard_mqtt_client.username_pw_set(tb_access_token)
        thingsboard_mqtt_client.on_connect = on_tb_connect
        thingsboard_mqtt_client.on_disconnect = on_tb_disconnect

    logging.info(f"--- Starting IoT Sensor Simulator ---")
    logging.info(f"  Asset ID: {sensor.asset_id}")
    logging.info(f"  INTERNAL MQTT Broker: {internal_broker_hostname}:{internal_broker_port} | Topic: {internal_topic}")
    logging.info(f"  THINGSBOARD MQTT Broker: {tb_host}:{tb_port} | User (Token): {tb_access_token[:5]}...")

    try:
        # Connect clients
        internal_mqtt_client.connect(internal_broker_hostname, internal_broker_port, 60)
        internal_mqtt_client.loop_start()

        if "YOUR_TURBINE_DEVICE_ACCESS_TOKEN" not in tb_access_token and tb_access_token:
            thingsboard_mqtt_client.connect(tb_host, tb_port, 60)
            thingsboard_mqtt_client.loop_start()

        while not is_internal_connected:
            logging.info("Waiting for INTERNAL MQTT connection...")
            time.sleep(1)

        iteration_count = 0
        is_currently_anomalous = False
        NORMAL_CYCLES = 15
        ANOMALY_CYCLES = 20

        while True:
            cycle_in_period = iteration_count % (NORMAL_CYCLES + ANOMALY_CYCLES)
            
            if cycle_in_period == 0 and is_currently_anomalous:
                logging.info(f"Ending anomaly period for {sensor.asset_id}")
                sensor.set_anomaly_status(False)
                is_currently_anomalous = False
            elif cycle_in_period == NORMAL_CYCLES and not is_currently_anomalous:
                logging.info(f"Starting anomaly period for {sensor.asset_id}")
                sensor.set_anomaly_status(True)
                is_currently_anomalous = True

            internal_packet, telemetry_packet = sensor.generate_data()
            
            # Publish to Internal Broker
            if is_internal_connected:
                internal_payload = json.dumps(internal_packet)
                internal_mqtt_client.publish(internal_topic, internal_payload)
            
            # Publish to ThingsBoard
            if is_tb_connected:
                tb_payload = json.dumps(telemetry_packet)
                thingsboard_mqtt_client.publish(tb_topic, tb_payload)

            logging.info(f"Cycle {iteration_count + 1}: Published data. Anomaly: {is_currently_anomalous}")
            
            iteration_count += 1
            time.sleep(sensor_data_interval)

    except KeyboardInterrupt:
        logging.info("\nIoT Sensor Simulator stopped by user.")
    except Exception as e:
        logging.error(f"An unexpected error occurred in IoT Sensor Simulator:", exc_info=True)
    finally:
        internal_mqtt_client.loop_stop()
        internal_mqtt_client.disconnect()
        thingsboard_mqtt_client.loop_stop()
        thingsboard_mqtt_client.disconnect()
        logging.info("MQTT clients disconnected.")