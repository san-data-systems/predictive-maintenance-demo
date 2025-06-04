# pcai_app/main_agent.py

import yaml
from flask import Flask, request, jsonify
import datetime
import os

# Import components from within the pcai_app package
from .api_connector import OpsRampConnector, ServiceNowConnector
from .rag_components import RAGSystem

# --- Global Variables & Configuration Loading ---
CONFIG = {}
APP_NAME = "PCAIAgentApplication"

# Initialize Flask app
app = Flask(__name__)

# Initialize components (will be done properly in main after loading config)
opsramp_connector: OpsRampConnector = None
servicenow_connector: ServiceNowConnector = None
rag_system: RAGSystem = None
pcai_agent_id_prefix: str = "PCAI_Agent_Default"
default_gear_part_number: str = "P/N G-0000"
default_bearing_part_number: str = "P/N B-0000"
simulated_diagnosis_confidence: float = 0.90

def load_configuration(config_path="config/demo_config.yaml"):
    """Loads configuration from the YAML file."""
    global CONFIG, pcai_agent_id_prefix, default_gear_part_number, default_bearing_part_number, simulated_diagnosis_confidence
    try:
        # Adjust path if main_agent.py is run from a different CWD
        # Assuming project root is the CWD when running Flask app typically
        effective_config_path = config_path
        if not os.path.exists(effective_config_path):
            # Try path relative to this file's directory if running script directly from pcai_app
            script_dir = os.path.dirname(__file__)
            effective_config_path = os.path.join(script_dir, "..", config_path) # Go up one level for config/
            if not os.path.exists(effective_config_path):
                 app.logger.error(f"Configuration file not found at {config_path} or {effective_config_path}")
                 raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(effective_config_path, 'r') as f:
            CONFIG = yaml.safe_load(f)
            app.logger.info(f"Successfully loaded configuration from {effective_config_path}")

        # Get company name for dynamic ID generation
        company_name = CONFIG.get('company_name_short', 'DefaultCo')
        pcai_agent_id_prefix = CONFIG.get('pcai_app', {}).get('agent_id_prefix_template', "PCAI_Agent_{company_name_short}").format(company_name_short=company_name)
        
        default_gear_part_number = CONFIG.get('pcai_app', {}).get('servicenow', {}).get('default_gear_part_number', default_gear_part_number)
        default_bearing_part_number = CONFIG.get('pcai_app', {}).get('servicenow', {}).get('default_bearing_part_number', default_bearing_part_number)
        simulated_diagnosis_confidence = CONFIG.get('pcai_app', {}).get('diagnosis', {}).get('simulated_diagnosis_confidence', simulated_diagnosis_confidence)

    except Exception as e:
        app.logger.error(f"Error loading configuration: {e}", exc_info=True)
        # Fallback to empty config to avoid crashing, but app might not work
        CONFIG = {}


def initialize_services():
    """Initializes connector and RAG services based on loaded configuration."""
    global opsramp_connector, servicenow_connector, rag_system

    if not CONFIG:
        app.logger.error("Cannot initialize services: Configuration is not loaded.")
        return

    pcai_config = CONFIG.get('pcai_app', {})
    opsramp_cfg = pcai_config.get('opsramp', {})
    servicenow_cfg = pcai_config.get('servicenow', {})
    kb_path = pcai_config.get('knowledge_base_path', 'knowledge_base_files/') # Default path

    opsramp_connector = OpsRampConnector(opsramp_config=opsramp_cfg, pcai_agent_id=pcai_agent_id_prefix)
    servicenow_connector = ServiceNowConnector(servicenow_config=servicenow_cfg)
    rag_system = RAGSystem(knowledge_base_path=kb_path)
    app.logger.info("PCAI Services (OpsRamp, ServiceNow, RAG) initialized.")


@app.route('/api/v1/analyze_trigger', methods=['POST'])
def analyze_trigger():
    """
    API Endpoint to receive anomaly triggers from the Edge Simulator.
    Orchestrates the RAG diagnosis and ServiceNow workflow.
    """
    if not all([opsramp_connector, servicenow_connector, rag_system]):
        app.logger.error("PCAI services not initialized. Cannot process request.")
        return jsonify({"status": "error", "message": "PCAI services not ready"}), 503

    try:
        trigger_data = request.get_json()
        if not trigger_data:
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        asset_id = trigger_data.get("asset_id", "UnknownAsset")
        edge_anomalies = trigger_data.get("edge_detected_anomalies", [])
        live_sensor_data = trigger_data.get("full_sensor_data_at_trigger", {})

        app.logger.info(f"Received trigger for asset: {asset_id} from {trigger_data.get('source_component')}")
        opsramp_connector.send_pcai_log(
            asset_id=asset_id,
            log_level="INFO",
            message=f"Received edge alert from {trigger_data.get('source_component')}. Initiating advanced analysis and RAG diagnosis.",
            details={"trigger_data": trigger_data}
        )
        opsramp_connector.send_pcai_log(
            asset_id=asset_id,
            log_level="RAG_ACCESS", # Custom log level for OpsRamp filtering
            message="Accessing live sensor data stream for RAG context.",
            details={"live_data_sample": {k: live_sensor_data.get(k) for k in ['temperature_c', 'temperature_increase_c', 'vibration_anomaly_signature_freq_hz', 'vibration_anomaly_signature_amp_g']}}
        )

        # --- RAG Powered Diagnosis ---
        # For demo, derive search terms based on known anomaly signatures
        search_terms_for_rag = ["failure", "maintenance", "vibration", "temperature", "acoustic"]
        if live_sensor_data.get("vibration_anomaly_signature_freq_hz"):
            search_terms_for_rag.append(f"{int(live_sensor_data['vibration_anomaly_signature_freq_hz'])}hz")
            search_terms_for_rag.append("gearbox") # Common context for vibration
        if live_sensor_data.get("temperature_increase_c", 0) > 3: # If notable temp increase
            search_terms_for_rag.append("overheating")
        
        # Pass live sensor data to RAG for context-aware retrieval
        rag_snippets = rag_system.query_knowledge_base(asset_id, live_sensor_data, list(set(search_terms_for_rag)))

        for snippet in rag_snippets:
            # Extract source file for a cleaner message
            source_file = snippet.split(":")[0] if ":" in snippet else "KnowledgeBase"
            opsramp_connector.send_pcai_log(
                asset_id=asset_id,
                log_level="RAG_RESULT",
                message=f"RAG: Querying Knowledge Base ({source_file})... Found: '{snippet}'",
                details={"retrieved_snippet": snippet}
            )

        # --- Simplified "Agentic" Decision Logic for Demo Narrative ---
        # This logic is tailored to match the demo script's expected outcome.
        diagnosis_made = False
        final_diagnosis_summary = "Further investigation required by technician."
        recommended_action_details = "Schedule standard inspection based on edge alert."
        priority_level = "MEDIUM"
        parts_to_recommend = []
        confidence = 0.65 # Default lower confidence

        # Check for "Gear Tooth Pitting" specific demo path
        # Condition: Vibration ~120Hz AND Temp Increase > 5C AND RAG found relevant snippets
        vib_freq = live_sensor_data.get("vibration_anomaly_signature_freq_hz")
        temp_increase = live_sensor_data.get("temperature_increase_c", 0.0)
        
        found_gear_pitting_kb = any("gear tooth pitting" in s.lower() and ("115-125hz" in s.lower() or "high-frequency" in s.lower()) for s in rag_snippets)
        found_temp_correlation_kb = any("oil temperature" in s.lower() and "rise >5°c" in s.lower() for s in rag_snippets)
        
        app.logger.info(f"Checking demo path: VibFreq={vib_freq}, TempInc={temp_increase}, GearPittingKB={found_gear_pitting_kb}, TempCorrKB={found_temp_correlation_kb}")

        if vib_freq and (115 <= vib_freq <= 125) and temp_increase > 4.5 and \
           (found_gear_pitting_kb or found_temp_correlation_kb): # Making it OR for demo robustness
            
            confidence = simulated_diagnosis_confidence # Use configured confidence for demo path
            final_diagnosis_summary = (
                f"Probable Gear Tooth Pitting (Stage 2 Degradation) on {asset_id}, Gearbox Assembly Alpha. "
                f"Primary Indicator: {live_sensor_data.get('vibration_anomaly_signature_amp_g')}g at {vib_freq}Hz vibration spike. "
                f"Corroborating: {temp_increase}°C oil temp increase."
            )
            recommended_action_details = (
                f"Schedule priority inspection and replacement of Gear Set {default_gear_part_number} "
                f"and Bearing Assembly {default_bearing_part_number} within 72 hours."
            )
            priority_level = "HIGH"
            parts_to_recommend = [default_gear_part_number, default_bearing_part_number]
            diagnosis_made = True
            app.logger.info(f"Demo-specific diagnosis path triggered for Gear Tooth Pitting on {asset_id}.")

        # Log final diagnosis
        opsramp_connector.send_pcai_log(
            asset_id=asset_id,
            log_level="WARN" if priority_level == "HIGH" else "INFO", # Use WARN for critical diagnosis
            message=f"Diagnosis Confidence: {confidence*100:.0f}%. {final_diagnosis_summary}",
            details={"confidence": confidence, "summary": final_diagnosis_summary}
        )
        opsramp_connector.send_pcai_log(
            asset_id=asset_id,
            log_level="INFO",
            message=f"Recommended Action: {recommended_action_details}",
            details={"action": recommended_action_details, "parts": parts_to_recommend}
        )

        # --- Automated Remediation Workflow (ServiceNow) ---
        if diagnosis_made and priority_level == "HIGH": # Only create WO for high priority confirmed issues
            opsramp_connector.send_pcai_log(
                asset_id=asset_id,
                log_level="INFO",
                message="Initiating automated Work Order creation in ServiceNow...",
                details={}
            )
            try:
                sn_response = servicenow_connector.create_work_order(
                    asset_id=asset_id,
                    short_description=f"AI DETECTED: Probable Gear Tooth Pitting - {asset_id}",
                    description=final_diagnosis_summary + f"\n\nRecommended Action: {recommended_action_details}",
                    priority=priority_level,
                    assignment_group=CONFIG.get('pcai_app',{}).get('servicenow',{}).get('default_assignment_group',"DefaultGroup"),
                    recommended_parts=parts_to_recommend
                )
                work_order_id = sn_response.get("work_order_id", "N/A")
                opsramp_connector.send_pcai_log(
                    asset_id=asset_id,
                    log_level="SUCCESS", # Custom level for success
                    message=f"Work Order {work_order_id} successfully created and populated in ServiceNow.",
                    details={"service_now_work_order_id": work_order_id, "response": sn_response}
                )
            except Exception as e_sn:
                app.logger.error(f"Error creating ServiceNow ticket for {asset_id}: {e_sn}", exc_info=True)
                opsramp_connector.send_pcai_log(
                    asset_id=asset_id,
                    log_level="ERROR",
                    message=f"Failed to create Work Order in ServiceNow. Error: {e_sn}",
                    details={"error": str(e_sn)}
                )
        else:
             app.logger.info(f"Skipping ServiceNow ticket creation for {asset_id} (diagnosis not critical or not made).")


        return jsonify({"status": "success", "message": f"Analysis complete for {asset_id}. Diagnosis: {final_diagnosis_summary}"}), 200

    except Exception as e:
        app.logger.error(f"Error during /analyze_trigger for asset {asset_id if 'asset_id' in locals() else 'Unknown'}: {e}", exc_info=True)
        if opsramp_connector and 'asset_id' in locals(): # Try to log error to OpsRamp
             opsramp_connector.send_pcai_log(asset_id, "ERROR", f"Internal PCAI Agent error: {e}", {"error_details": str(e)})
        return jsonify({"status": "error", "message": "Internal server error during analysis"}), 500


if __name__ == '__main__':
    load_configuration() # Load config before initializing services
    initialize_services()  # Initialize after config is loaded

    host = CONFIG.get('pcai_app', {}).get('listen_host', '0.0.0.0')
    port = CONFIG.get('pcai_app', {}).get('listen_port', 5000)
    
    app.logger.info(f"Starting {APP_NAME} Flask server on {host}:{port}")
    app.run(host=host, port=port, debug=True) # debug=True is useful for development