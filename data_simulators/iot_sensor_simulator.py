# data_simulat/iot_sensor_simulator.py

import paho.mqtt.client as mqtt
import time
import json
import logging
import random
from datetime import datetime, timezone

from utilities.common_utils import get_full_config

# Configure logging for the module
logger = logging.getLogger(__name__)

def setup_mqtt_client(client_id_prefix, config):
    """
    Sets up an MQTT client with common callbacks for connection/disconnection.
    """
    # For ThingsBoard, client_id is typically derived from the device token, so empty
    # For Internal, a unique client_id is generated to prevent conflicts
    client_id = "" if client_id_prefix == "ThingsBoard" else f"{client_id_prefix}-{int(time.time())}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    
    # ThingsBoard requires device token as username
    token = config.get('device_token')
    if token and token not in ('YOUR_THINGSBOARD_DEVICE_TOKEN', 'PASTE_YOUR_REAL_THINGSBOARD_TOKEN_HERE'):
        client.username_pw_set(token)

    def on_connect(c, userdata, flags, reason_code, props):
        """Callback for when the client connects to the MQTT broker."""
        if reason_code.is_failure:
            logger.warning(f"MQTT | Client '{client_id_prefix}' failed to connect: {reason_code}. Check broker status or credentials.")
        else:
            logger.info(f"MQTT | Client '{client_id_prefix}' successfully connected.")

    def on_disconnect(c, userdata, flags, reason_code, props):
        """Callback for when the client disconnects from the MQTT broker."""
        if reason_code and not reason_code.is_failure:
            logger.info(f"MQTT | Client '{client_id_prefix}' disconnected cleanly (Reason: {reason_code}).")
        else:
            logger.warning(f"MQTT | Client '{client_id_prefix}' unexpectedly disconnected (Reason: {reason_code}). Attempting silent reconnect in background.")
            
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    return client

def attempt_reconnect(client, name, config):
    """
    Attempts to connect or reconnect an MQTT client asynchronously if not already connected.
    """
    if not client.is_connected():
        try:
            logger.info(f"MQTT | Attempting to connect '{name}' to {config['host']}:{config['port']}...")
            client.connect_async(config['host'], config['port'], 60) # 60-second keepalive
        except Exception as e:
            logger.error(f"MQTT | Error initiating connection for '{name}': {e}")

if __name__ == "__main__":
    # Basic logging configuration for console output
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)-8s - %(name)-15s - %(message)s"
    )
    # Re-get logger after basicConfig to ensure it uses the new format
    logger = logging.getLogger(__name__)

    # Load full configuration from common_utils
    cfg = get_full_config()
    if not cfg:
        logger.critical("FATAL: Could not load configuration. Exiting.")
        exit(1)

    # --- Load specific configuration sections ---
    sensor_cfg = cfg.get('iot_sensor_simulator', {})
    mqtt_cfg   = cfg.get('mqtt', {})
    tb_cfg     = cfg.get('thingsboard', {})
    company    = cfg.get('company_name_short', 'DefaultCo')

    # --- Build asset ID for the simulated turbine ---
    prefix_tpl           = sensor_cfg.get('asset_id_prefix', "{company_name_short}_Turbine")
    asset_prefix         = prefix_tpl.format(company_name_short=company)
    default_number       = sensor_cfg.get('default_asset_number', 7)
    asset_id             = f"{asset_prefix}{str(default_number).zfill(3)}"
    logger.info(f"[Sensor Simulation | {asset_id}] Initialized.")

    # --- Initialize MQTT clients ---
    logger.info("--- Initializing MQTT clients in disconnected state ---")
    internal_client = setup_mqtt_client("Internal", mqtt_cfg)
    tb_client       = setup_mqtt_client("ThingsBoard", tb_cfg)
    
    # Start MQTT client loops in background threads to handle connections/disconnections
    internal_client.loop_start()
    tb_client.loop_start()

    # --- FSM (Finite State Machine) and Threshold Parameters ---
    # Normal operating ranges for sensor metrics (from config)
    vib_range  = sensor_cfg.get('vibration_normal_range', [0.1, 0.5]) # g (gravitational force)
    acou_range = sensor_cfg.get('acoustic_normal_range', [20.0, 35.0]) # dB (decibels)
    base_temp  = sensor_cfg.get('base_temp_c', 42.0) # °C (Celsius)

    # Base values for jittering in the 'normal' phase (mid-point of normal range)
    VIB_BASE   = sum(vib_range) / 2.0
    TEMP_BASE  = base_temp
    ACOU_BASE  = sum(acou_range) / 2.0

    # Anomaly thresholds (target values for metrics during anomaly peak)
    # These values are designed to be clearly outside the 'normal' range
    VIB_THRESHOLD  = vib_range[1] * sensor_cfg.get('anomaly_vibration_factor', 5.0) # e.g., 0.5g * 5.0 = 2.5g peak
    TEMP_THRESHOLD = base_temp + sensor_cfg.get('temperature_critical_c_increase', 15.0) # e.g., 42.0 + 15.0 = 57.0°C peak
    ACOU_THRESHOLD = acou_range[1] * sensor_cfg.get('acoustic_anomaly_factor', 1.5) # e.g., 35.0dB * 1.5 = 52.5dB peak

    # FSM timing and probability parameters (from config)
    INTERVAL            = sensor_cfg.get('data_interval_seconds', 10) # How often to generate data
    START_CHANCE        = sensor_cfg.get('anomaly_start_chance', 0.15) # Probability of an anomaly starting AFTER initial_normal_ticks
    
    # Define distinct ramp duration and hold duration for clarity and control
    RAMP_DURATION_TICKS = sensor_cfg.get('anomaly_ramp_duration_ticks', 10) # How many intervals to ramp up/down
    HOLD_TICKS          = sensor_cfg.get('hold_duration_ticks', 15)       # How many intervals to hold at anomaly peak
    
    # Initial guaranteed normal period at the start of the simulation
    INITIAL_NORMAL_TICKS = sensor_cfg.get('initial_normal_ticks', 6)

    # Standard deviation for Gaussian noise in the 'normal' phase
    NORMAL_JITTER_STD_DEV_VIB  = sensor_cfg.get('normal_jitter_std_dev_vib', 0.02)
    NORMAL_JITTER_STD_DEV_TEMP = sensor_cfg.get('normal_jitter_std_dev_temp', 0.2)
    NORMAL_JITTER_STD_DEV_ACOU = sensor_cfg.get('normal_jitter_std_dev_acou', 0.5)

    # Common influence factor for normal jitter (for subtle correlation)
    COMMON_NORMAL_JITTER_STD_DEV = sensor_cfg.get('common_normal_jitter_std_dev', 0.005) # StDev for the common component
    COMMON_NORMAL_JITTER_INFLUENCE_SCALE_VIB = sensor_cfg.get('common_normal_jitter_influence_scale_vib', 1.0)
    COMMON_NORMAL_JITTER_INFLUENCE_SCALE_TEMP = sensor_cfg.get('common_normal_jitter_influence_scale_temp', 10.0) # Temp reacts more to common changes
    COMMON_NORMAL_JITTER_INFLUENCE_SCALE_ACOU = sensor_cfg.get('common_normal_jitter_influence_scale_acou', 5.0) # Acoustic reacts moderately

    # Multiplier for jitter during anomaly phases (more chaotic)
    ANOMALY_JITTER_FACTOR = sensor_cfg.get('anomaly_jitter_factor', 2.0)

    # Anomaly-specific frequencies for ThingsBoard (decoupled from amplitude)
    ANOMALY_DOMINANT_FREQ = float(sensor_cfg.get('anomaly_dominant_frequency_hz', 121.0))
    ANOMALY_SIGNATURE_FREQ = float(sensor_cfg.get('anomaly_signature_frequency_hz', 121.38))

    # Steps to ramp up/down gradually (calculated based on desired duration)
    RAMP_UP_STEP = {
        'vib':  (VIB_THRESHOLD  - VIB_BASE)  / RAMP_DURATION_TICKS,
        'temp': (TEMP_THRESHOLD - TEMP_BASE) / RAMP_DURATION_TICKS,
        'acou': (ACOU_THRESHOLD - ACOU_BASE) / RAMP_DURATION_TICKS
    }
    # Ramp down at the same rate as ramp up
    RAMP_DOWN_STEP = RAMP_UP_STEP.copy()

    # NEW: Small epsilon for floating point comparisons in state transitions
    EPSILON_FOR_TRANSITION = 0.001 

    # --- FSM state initialization ---
    current_vib   = VIB_BASE
    current_temp  = TEMP_BASE
    current_acou  = ACOU_BASE
    phase         = 'normal'
    hold_counter  = 0
    normal_ticks_counter = 0 # Counter for initial normal period and subsequent normal phases

    logger.info("--- Starting IoT Sensor Simulation (Press Ctrl+C to stop) ---")

    try:
        while True:
            # --- FSM state transitions and metric adjustments ---
            if phase == 'normal':
                # Apply a common random influence first for subtle correlation
                common_fluctuation = random.gauss(0, COMMON_NORMAL_JITTER_STD_DEV)
                current_vib  += common_fluctuation * COMMON_NORMAL_JITTER_INFLUENCE_SCALE_VIB
                current_temp += common_fluctuation * COMMON_NORMAL_JITTER_INFLUENCE_SCALE_TEMP
                current_acou += common_fluctuation * COMMON_NORMAL_JITTER_INFLUENCE_SCALE_ACOU

                # Apply individual sensor noise using Gaussian distribution
                current_vib  += random.gauss(0, NORMAL_JITTER_STD_DEV_VIB)
                current_temp += random.gauss(0, NORMAL_JITTER_STD_DEV_TEMP)
                current_acou += random.gauss(0, NORMAL_JITTER_STD_DEV_ACOU)

                # Clamp metrics within their normal operating ranges for stability
                current_vib  = max(vib_range[0], min(vib_range[1], current_vib))
                current_temp = max(base_temp - 2.0, min(base_temp + 2.0, current_temp)) # Small flexible range around base temp
                current_acou = max(acou_range[0], min(acou_range[1], current_acou))

                # Transition logic for 'normal' phase
                if normal_ticks_counter < INITIAL_NORMAL_TICKS:
                    normal_ticks_counter += 1
                    if normal_ticks_counter == INITIAL_NORMAL_TICKS:
                         logger.info(f"Normal operating period complete ({INITIAL_NORMAL_TICKS} intervals). Anomaly chance now active.")
                else:
                    if random.random() < START_CHANCE:
                        phase = 'ramp_up'
                        hold_counter = 0
                        normal_ticks_counter = 0 # Reset counter for next normal phase
                        logger.warning(
                            f">>> Starting anomaly cycle: Transitioning to ramp_up. "
                            f"Current values: Vib={current_vib:.4f}g, Temp={current_temp:.4f}°C, Acou={current_acou:.4f}dB <<<"
                        )

            elif phase == 'ramp_up':
                # Gradually increase metrics towards anomaly thresholds with added, larger jitter
                current_vib  += RAMP_UP_STEP['vib'] + random.gauss(0, NORMAL_JITTER_STD_DEV_VIB * ANOMALY_JITTER_FACTOR)
                current_temp += RAMP_UP_STEP['temp'] + random.gauss(0, NORMAL_JITTER_STD_DEV_TEMP * ANOMALY_JITTER_FACTOR)
                current_acou += RAMP_UP_STEP['acou'] + random.gauss(0, NORMAL_JITTER_STD_DEV_ACOU * ANOMALY_JITTER_FACTOR)
                
                # Ensure values don't overshoot target thresholds excessively
                current_vib = min(VIB_THRESHOLD * 1.1, current_vib) # Allow slight overshoot to ensure threshold crossing
                current_temp = min(TEMP_THRESHOLD * 1.1, current_temp)
                current_acou = min(ACOU_THRESHOLD * 1.1, current_acou)

                # Once all metrics cross their thresholds, move to hold phase
                if (current_vib  >= VIB_THRESHOLD and
                    current_temp >= TEMP_THRESHOLD and
                    current_acou >= ACOU_THRESHOLD):
                    phase = 'hold'
                    logger.info(
                        f"+++ Anomaly thresholds reached, entering hold phase. "
                        f"Current values: Vib={current_vib:.4f}g, Temp={current_temp:.4f}°C, Acou={current_acou:.4f}dB +++"
                    )

            elif phase == 'hold':
                # Maintain anomaly state at high levels with increased jitter
                current_vib  = VIB_THRESHOLD + random.gauss(0, NORMAL_JITTER_STD_DEV_VIB * ANOMALY_JITTER_FACTOR * 1.5) # Jitter around threshold
                current_temp = TEMP_THRESHOLD + random.gauss(0, NORMAL_JITTER_STD_DEV_TEMP * ANOMALY_JITTER_FACTOR * 1.5)
                current_acou = ACOU_THRESHOLD + random.gauss(0, NORMAL_JITTER_STD_DEV_ACOU * ANOMALY_JITTER_FACTOR * 1.5)
                
                hold_counter += 1
                if hold_counter >= HOLD_TICKS:
                    phase = 'ramp_down'
                    logger.info(
                        f"--- Exiting hold phase, beginning ramp-down. "
                        f"Current values: Vib={current_vib:.4f}g, Temp={current_temp:.4f}°C, Acou={current_acou:.4f}dB ---"
                    )

            elif phase == 'ramp_down':
                # Gradually decrease metrics back towards normal baseline with added, larger jitter
                current_vib  -= RAMP_DOWN_STEP['vib'] + random.gauss(0, NORMAL_JITTER_STD_DEV_VIB * ANOMALY_JITTER_FACTOR)
                current_temp -= RAMP_DOWN_STEP['temp'] + random.gauss(0, NORMAL_JITTER_STD_DEV_TEMP * ANOMALY_JITTER_FACTOR)
                current_acou -= RAMP_DOWN_STEP['acou'] + random.gauss(0, NORMAL_JITTER_STD_DEV_ACOU * ANOMALY_JITTER_FACTOR)
                
                # Removed direct clamping here to allow values to drop below BASE for easier transition trigger
                # The explicit setting in the 'if' block handles snapping to BASE.

                # Check if all values have reached or fallen below their base values (with tolerance)
                if (current_vib  <= VIB_BASE + EPSILON_FOR_TRANSITION and
                    current_temp <= TEMP_BASE + EPSILON_FOR_TRANSITION and
                    current_acou <= ACOU_BASE + EPSILON_FOR_TRANSITION):
                    # Explicitly set to base values for a smooth reset before going back to normal jitter
                    current_vib, current_temp, current_acou = VIB_BASE, TEMP_BASE, ACOU_BASE
                    phase = 'normal'
                    normal_ticks_counter = 0 # Reset counter when back to normal for next guaranteed period
                    logger.info(
                        f"<<< Anomaly cycle complete, back to normal. "
                        f"Final values: Vib={current_vib:.4f}g, Temp={current_temp:.4f}°C, Acou={current_acou:.4f}dB >>>"
                    )

            # --- Build payloads for MQTT ---
            # ISO 8601 with Z for UTC and milliseconds precision
            timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds') + "Z" 

            # Payload for internal MQTT broker (simpler format for internal processing)
            internal = {
                "assetId":           asset_id,
                "timestamp":         timestamp,
                "vibration":         round(current_vib, 4), # Overall amplitude in g
                "temperature":       round(current_temp, 4), # Temperature in C
                "acoustic":          round(current_acou, 4), # Acoustic in dB
                "status":            "ANOMALY" if phase != 'normal' else "NORMAL", # Current operational status
                "anomalyInjected":   phase != 'normal', # Boolean flag
                # NEW: Add keys needed by aruba_edge_simulator for detection
                "vibration_overall_amplitude_g": round(current_vib, 4), # Explicitly include overall amplitude
                "vibration_dominant_frequency_hz": round(ANOMALY_DOMINANT_FREQ if phase!='normal' else random.uniform(55, 65), 4) # Include dominant freq
            }

            # Payload for ThingsBoard MQTT broker (specific telemetry keys matching dashboard expectations)
            tb_payload = {
                "temperature_c":                     round(current_temp, 4),
                "acoustic_critical_band_db":         round(current_acou, 4),
                "is_anomaly_induced":                str(phase != 'normal').lower(), # ThingsBoard prefers lowercase boolean strings for dashboard widgets
                "temperature_increase_c":            max(0, round(current_temp - base_temp, 4)), # How much temperature increased from baseline
                "vibration_overall_amplitude_g":     round(current_vib, 4),
                
                # Anomaly frequencies are now decoupled from amplitude, crucial for frequency-based detection
                "vibration_dominant_frequency_hz":   round(ANOMALY_DOMINANT_FREQ if phase!='normal' else random.uniform(55, 65), 4),
                "vibration_anomaly_signature_amp_g": round(current_vib if phase!='normal' else 0.0, 4), # Anomaly signature amplitude (can be same as overall for simplicity)
                "vibration_anomaly_signature_freq_hz": round(ANOMALY_SIGNATURE_FREQ if phase!='normal' else 0.0, 4)
            }

            # --- Publish to Internal MQTT broker ---
            attempt_reconnect(internal_client, "Internal", mqtt_cfg)
            if internal_client.is_connected():
                internal_client.publish(
                    mqtt_cfg['sensor_topic'], # Topic defined in config
                    json.dumps(internal),
                    qos=1 # Quality of Service 1: At least once delivery
                )
                logger.info(f"SENSOR | Generated data: Temp={internal['temperature']}°C, Vib={internal['vibration']}g, Status={internal['status']}")
                logger.debug(f"MQTT | Published internal payload: {json.dumps(internal)}")
            else:
                logger.warning("MQTT | Internal broker not connected. Skipping internal publish.")

            # --- Publish to ThingsBoard MQTT broker ---
            attempt_reconnect(tb_client, "ThingsBoard", tb_cfg)
            if tb_client.is_connected():
                tb_client.publish(
                    'v1/devices/me/telemetry', # Standard ThingsBoard telemetry topic for device telemetry
                    json.dumps(tb_payload),
                    qos=1 # Quality of Service 1: At least once delivery
                )
                logger.debug(f"MQTT | Published to ThingsBoard: {json.dumps(tb_payload)}")
            else:
                logger.warning("MQTT | ThingsBoard broker not connected. Skipping ThingsBoard publish.")

            time.sleep(INTERVAL) # Pause for the defined interval before the next data point

    except KeyboardInterrupt:
        logger.info("Simulation stopped by user (Ctrl+C).")
    finally:
        logger.info("--- Cleaning up MQTT clients ---")
        # Stop the MQTT client loops
        internal_client.loop_stop()
        tb_client.loop_stop()
        # Disconnect clients if they are still connected
        if internal_client.is_connected():
            internal_client.disconnect()
        if tb_client.is_connected():
            tb_client.disconnect()
        logger.info("Clean shutdown complete.")