# pcai_app/main_agent.py

from flask import Flask, request, jsonify
import os
import logging 

from utilities import get_utc_timestamp, get_full_config 

from .api_connector import OpsRampConnector, ServiceNowConnector, OllamaConnector
from .rag_components import RAGSystem

CONFIG = {} 
APP_NAME = "PCAIAgentApplication_LLM_RealSN"

app = Flask(__name__)

# Configure Flask logger for better output (if not already configured by Flask/Werkzeug in debug)
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true": # Avoid reconfiguring in reloader
    app.logger.setLevel(logging.INFO)
    # Check if a stream handler for console output already exists
    if not any(isinstance(h, logging.StreamHandler) for h in app.logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
        ))
        app.logger.addHandler(handler)
    app.logger.propagate = False


opsramp_connector: OpsRampConnector = None
servicenow_connector: ServiceNowConnector = None
rag_system: RAGSystem = None
llm_connector: OllamaConnector = None 
pcai_agent_id_prefix: str = "PCAI_Agent_Default"

def load_configuration():
    global CONFIG, pcai_agent_id_prefix
    app.logger.info("Attempting to load configuration using common_utils...")
    CONFIG = get_full_config() 
    if not CONFIG:
        app.logger.critical("CRITICAL: Configuration could not be loaded. PCAI Agent may not function correctly.")
        return False

    pcai_app_cfg = CONFIG.get('pcai_app', {})
    company_name = CONFIG.get('company_name_short', 'DefaultCo')
    template = pcai_app_cfg.get('agent_id_prefix_template', "PCAI_Agent_{company_name_short}")
    pcai_agent_id_prefix = template.format(company_name_short=company_name)
    
    app.logger.info(f"Successfully loaded configuration for PCAI Agent ({pcai_agent_id_prefix}).")
    return True

def initialize_services():
    global opsramp_connector, servicenow_connector, rag_system, llm_connector
    app.logger.info("Attempting to initialize PCAI services...")
    if not CONFIG: # Should have been loaded by load_configuration()
        app.logger.error("Cannot initialize services: Global CONFIG is not loaded.")
        return False

    pcai_config = CONFIG.get('pcai_app', {})
    opsramp_cfg = pcai_config.get('opsramp', {})
    servicenow_cfg = pcai_config.get('servicenow', {})
    kb_path = pcai_config.get('knowledge_base_path', 'knowledge_base_files/')
    
    llm_provider_config = pcai_config.get('llm_config', {})
    ollama_cfg = llm_provider_config.get('ollama') if llm_provider_config.get('provider') == 'ollama' else None

    services_initialized_correctly = True

    try:
        opsramp_connector = OpsRampConnector(opsramp_config=opsramp_cfg, pcai_agent_id=pcai_agent_id_prefix)
        servicenow_connector = ServiceNowConnector(servicenow_config=servicenow_cfg) # Errors handled inside
        rag_system = RAGSystem(knowledge_base_path=kb_path)
    except Exception as e:
        app.logger.critical(f"CRITICAL: Error initializing core connectors (OpsRamp, ServiceNow, RAG): {e}", exc_info=True)
        services_initialized_correctly = False
    
    if not ollama_cfg:
        app.logger.warning("LLM (Ollama) configuration ('llm_config.ollama') not found or provider not 'ollama'. LLM functionality will be disabled.")
        llm_connector = None
    else:
        try:
            llm_connector = OllamaConnector(ollama_config=ollama_cfg)
            if not llm_connector.client:
                 app.logger.error("OllamaConnector client failed to initialize (e.g., Ollama server connection error during init). LLM calls will fail.")
                 # Continue, but the check in analyze_trigger will prevent LLM use
        except Exception as e:
            app.logger.critical(f"CRITICAL: Error during OllamaConnector instantiation: {e}", exc_info=True)
            llm_connector = None 
            services_initialized_correctly = False
            
    if services_initialized_correctly:
        app.logger.info("PCAI Services initialization attempt complete.")
    else:
        app.logger.error("One or more PCAI services failed to initialize correctly.")
    return services_initialized_correctly


def construct_llm_prompt(asset_id: str, live_sensor_data: dict, rag_snippets: list) -> str:
    # (This function is the same as the last version - ensure it's complete and correct)
    sensor_data_summary_lines = [f"Asset ID: {asset_id}"]
    if 'timestamp' in live_sensor_data:
        sensor_data_summary_lines.append(f"Timestamp of data: {live_sensor_data['timestamp']}")
    if 'temperature_c' in live_sensor_data:
        temp_line = f"Temperature: {live_sensor_data['temperature_c']}°C"
        if 'temperature_increase_c' in live_sensor_data:
            temp_line += f" (Increase from baseline: {live_sensor_data['temperature_increase_c']}°C)"
        sensor_data_summary_lines.append(temp_line)
    if 'vibration_overall_amplitude_g' in live_sensor_data and 'vibration_dominant_frequency_hz' in live_sensor_data:
        sensor_data_summary_lines.append(f"Overall Vibration: {live_sensor_data['vibration_overall_amplitude_g']}g @ {live_sensor_data['vibration_dominant_frequency_hz']}Hz")
    if live_sensor_data.get("vibration_anomaly_signature_freq_hz") and live_sensor_data.get("vibration_anomaly_signature_amp_g"):
        sensor_data_summary_lines.append(
            f"Specific Vibration Anomaly: {live_sensor_data['vibration_anomaly_signature_amp_g']}g "
            f"at {live_sensor_data['vibration_anomaly_signature_freq_hz']}Hz"
        )
    if 'acoustic_overall_db' in live_sensor_data:
        sensor_data_summary_lines.append(f"Acoustic Overall: {live_sensor_data['acoustic_overall_db']}dB")
    if 'acoustic_critical_band_db' in live_sensor_data:
        sensor_data_summary_lines.append(f"Acoustic Critical Band: {live_sensor_data['acoustic_critical_band_db']}dB")
    sensor_data_summary = "\n".join(sensor_data_summary_lines)
    knowledge_base_context = "Relevant information from knowledge base (if any):\n"
    if rag_snippets and rag_snippets[0] != "No specific KB articles found matching the immediate query criteria.":
        for i, snippet in enumerate(rag_snippets):
            knowledge_base_context += f"KB{i+1}: {snippet}\n"
    else:
        knowledge_base_context += "No specific highly relevant articles were found by the RAG system for the immediate sensor readings and query.\n"
    prompt = f"""You are an expert AI Predictive Maintenance diagnostician for industrial wind turbines, model GRX-II.
Your task is to analyze the provided live sensor data and contextual information from the knowledge base to diagnose potential faults.

Current Live Sensor Data:
{sensor_data_summary}

{knowledge_base_context}
Based on all the above information, please provide a diagnosis.
Your response MUST be a single, valid JSON object. Do not include any text outside of this JSON object.
The JSON object must have the following exact keys and data types:
- "diagnosis_summary": (string) A concise summary of the most probable fault. If no specific fault is clear, state that further investigation is needed.
- "confidence_percentage": (float) Your confidence in this diagnosis, as a percentage (e.g., 85.5 for 85.5%). If uncertain, provide a lower confidence (e.g., 30.0). This should be a numerical value.
- "reasoning": (string) A brief explanation of how you arrived at the diagnosis, referencing specific sensor data points and knowledge base snippets if applicable.
- "recommended_actions": (list of strings) A list of 1 to 3 actionable steps for maintenance personnel.
- "required_parts": (list of strings) A list of part numbers or names potentially required for the repair. Use an empty list [] if no specific parts can be determined, or ["N/A"] if not applicable.

Ensure the output is only the JSON object, starting with {{ and ending with }}.
Example of the required JSON output structure:
{{
  "diagnosis_summary": "Probable early-stage gear tooth pitting.",
  "confidence_percentage": 75.0,
  "reasoning": "High-frequency vibration (121Hz) and a 5.5°C temperature increase correlate with KB01 which mentions gear tooth pitting under similar conditions.",
  "recommended_actions": [
    "Schedule detailed inspection of the gearbox within 72 hours.",
    "Perform oil sample analysis for metal particles."
  ],
  "required_parts": ["P/N G-5432", "Gearbox Oil Type XYZ"]
}}

Now, generate ONLY the JSON output for the provided data:
"""
    return prompt

@app.route('/api/v1/analyze_trigger', methods=['POST'])
def analyze_trigger():
    app.logger.info("--- DEBUG: Entered /api/v1/analyze_trigger endpoint ---")

    services_ready_for_request = True
    if not opsramp_connector: app.logger.error("DEBUG: opsramp_connector is None"); services_ready_for_request = False
    if not servicenow_connector: app.logger.error("DEBUG: servicenow_connector is None"); services_ready_for_request = False
    if not rag_system: app.logger.error("DEBUG: rag_system is None"); services_ready_for_request = False
    if not llm_connector: 
        app.logger.error("DEBUG: llm_connector is None")
        services_ready_for_request = False
    elif not llm_connector.client: 
        app.logger.error("DEBUG: llm_connector.client is None or not usable")
        services_ready_for_request = False
    
    if not services_ready_for_request:
        app.logger.error("DEBUG: One or more critical PCAI services are not ready. Cannot process request.")
        return jsonify({"status": "error", "message": "PCAI services not ready or LLM connection failed"}), 503
    
    app.logger.info("DEBUG: All PCAI services checked and appear OK for this request.")

    trigger_data = None 
    asset_id = "UnknownAssetInTrigger" 
    try:
        trigger_data = request.get_json()
        if not trigger_data:
            app.logger.error("DEBUG: Invalid JSON payload or no payload received from edge.")
            return jsonify({"status": "error", "message": "Invalid JSON payload from edge"}), 400
        
        app.logger.info(f"DEBUG: Successfully got JSON payload. Keys: {list(trigger_data.keys())}")

        asset_id = trigger_data.get("asset_id", "UnknownAssetOnPayload")
        live_sensor_data = trigger_data.get("full_sensor_data_at_trigger", {})
        app.logger.info(f"DEBUG: Processing trigger for asset: {asset_id} from {trigger_data.get('source_component')}")

        opsramp_connector.send_pcai_log(asset_id, "INFO", f"Received edge alert. Initiating AI analysis.", {"trigger_summary": trigger_data.get("edge_detected_anomalies")})
        
        app.logger.info("DEBUG STEP 4: Before RAG query.")
        search_terms_for_rag = ["failure", "maintenance", "vibration", "temperature", "acoustic", "GRX-II", asset_id]
        if live_sensor_data.get("vibration_anomaly_signature_freq_hz"):
            search_terms_for_rag.append(f"{int(live_sensor_data['vibration_anomaly_signature_freq_hz'])}hz")
        rag_snippets = rag_system.query_knowledge_base(asset_id, live_sensor_data, list(set(search_terms_for_rag)))
        app.logger.info(f"DEBUG STEP 5: After RAG query. Snippets count: {len(rag_snippets)}. First: {rag_snippets[0] if rag_snippets else 'None'}")
        
        for idx, snippet in enumerate(rag_snippets):
            opsramp_connector.send_pcai_log(asset_id, "INFO", f"RAG Snippet {idx+1}: '{snippet[:200]}...'") # Log snippet summary

        app.logger.info("DEBUG STEP 6: Before constructing LLM prompt.")
        llm_prompt = construct_llm_prompt(asset_id, live_sensor_data, rag_snippets)
        app.logger.info(f"DEBUG STEP 7: After constructing LLM prompt (length: {len(llm_prompt)}).")
        
        opsramp_connector.send_pcai_log(asset_id, "INFO", f"Querying LLM ({llm_connector.model_name}) for diagnosis...")
        app.logger.info("DEBUG STEP 8: PRE-CALL to llm_connector.generate_structured_diagnosis.")
        llm_response_data = llm_connector.generate_structured_diagnosis(llm_prompt)
        app.logger.info(f"DEBUG STEP 9: POST-CALL to llm_connector.generate_structured_diagnosis.")
        
        # Default values
        final_diagnosis_summary = "LLM processing issue or no clear diagnosis."
        confidence = 0.0
        reasoning = "N/A"
        recommended_action_details_list = ["Manual inspection required."]
        parts_to_recommend = ["N/A"]
        priority_level = "MEDIUM"

        if isinstance(llm_response_data, dict) and "error" not in llm_response_data:
            app.logger.info(f"DEBUG: LLM Response (dict type) Keys: {list(llm_response_data.keys())}")
            final_diagnosis_summary = llm_response_data.get("diagnosis_summary", final_diagnosis_summary)
            try:
                confidence_val = llm_response_data.get("confidence_percentage", 0.0)
                confidence = float(confidence_val) / 100.0 if isinstance(confidence_val, (int, float)) else 0.0
            except (ValueError, TypeError):
                app.logger.warning(f"Could not parse LLM confidence '{llm_response_data.get('confidence_percentage')}' to float.")
            reasoning = llm_response_data.get("reasoning", "No reasoning from LLM.")
            recommended_action_details_list = llm_response_data.get("recommended_actions", recommended_action_details_list)
            if not isinstance(recommended_action_details_list, list): recommended_action_details_list = [str(recommended_action_details_list)]
            parts_to_recommend = llm_response_data.get("required_parts", parts_to_recommend)
            if not isinstance(parts_to_recommend, list): parts_to_recommend = [str(parts_to_recommend)]

            if confidence > 0.75 or any(kw in final_diagnosis_summary.lower() for kw in ["critical", "severe", "urgent", "immediate", "failure"]):
                priority_level = "HIGH"
            elif confidence > 0.50: priority_level = "MEDIUM"
            else: priority_level = "LOW"
            app.logger.info(f"LLM Diagnosis: Summary='{final_diagnosis_summary}', Confidence={confidence*100:.1f}%, Priority={priority_level}")
            opsramp_connector.send_pcai_log(asset_id, "INFO", f"LLM Reasoning: {reasoning}")
        else:
            app.logger.error(f"LLM interaction error or malformed data. Response: {str(llm_response_data)[:1000]}")
            opsramp_connector.send_pcai_log(asset_id, "ERROR", "LLM interaction failed or returned malformed data.", {"llm_error_response": str(llm_response_data)[:1000]})

        opsramp_connector.send_pcai_log(
            asset_id, "WARN" if priority_level == "HIGH" else "INFO",
            f"LLM Diagnosis. Confidence: {confidence*100:.1f}%. Summary: {final_diagnosis_summary}",
            {"confidence": f"{confidence*100:.1f}%", "summary": final_diagnosis_summary, "llm_response_snippet": str(llm_response_data)[:200]}
        )
        opsramp_connector.send_pcai_log(
            asset_id, "INFO", f"LLM Recommended Actions: {'; '.join(recommended_action_details_list)}",
            {"actions": recommended_action_details_list, "parts": parts_to_recommend}
        )

        # ServiceNow Ticket Creation
        sn_config = CONFIG.get('pcai_app',{}).get('servicenow',{})
        diagnosis_cfg = CONFIG.get('pcai_app',{}).get('diagnosis',{})
        confidence_threshold_sn = diagnosis_cfg.get('confidence_threshold_for_action', 0.70)

        if priority_level == "HIGH" and confidence >= confidence_threshold_sn and servicenow_connector and servicenow_connector.api_user:
            opsramp_connector.send_pcai_log(asset_id, "INFO", "Initiating ServiceNow Work Order (High Priority/Confidence).")
            # ... (ServiceNow creation logic as previously refined, ensure it uses ai_confidence, ai_reasoning etc.) ...
            try:
                sn_description = (
                    f"AI Diagnosis ({llm_connector.model_name if llm_connector else 'LLM'}):\n{final_diagnosis_summary}\n\n"
                    f"Confidence: {confidence*100:.1f}%\n"
                    f"AI Reasoning: {reasoning}\n\n"
                    f"Recommended Actions:\n- {'\n- '.join(recommended_action_details_list)}\n\n"
                    f"Potentially Required Parts: {', '.join(parts_to_recommend if parts_to_recommend else ['N/A'])}\n\n"
                    f"Key RAG Snippets Considered (up to 3):\n"
                )
                if rag_snippets and rag_snippets[0] != "No specific KB articles found matching the immediate query criteria.":
                     for rag_snip in rag_snippets[:3]: sn_description += f"- {rag_snip}\n"
                else:
                     sn_description += "- No specific KB articles retrieved or applicable.\n"

                sn_response = servicenow_connector.create_work_order(
                    asset_id=asset_id,
                    short_description=f"AI DETECTED ({priority_level}): {final_diagnosis_summary[:80]} - {asset_id}",
                    description=sn_description,
                    priority=priority_level,
                    assignment_group=sn_config.get('default_assignment_group',"DefaultGroup"),
                    recommended_parts=parts_to_recommend,
                    ai_confidence=confidence, # Pass confidence
                    ai_reasoning=reasoning,   # Pass reasoning
                    ai_recommended_actions=recommended_action_details_list # Pass actions
                )
                work_order_id = sn_response.get("work_order_id", "N/A")
                opsramp_connector.send_pcai_log(asset_id, "INFO", f"Work Order {work_order_id} successfully created in ServiceNow.", {"service_now_work_order_id": work_order_id, "sn_response_status": sn_response.get("status")}) 
            except Exception as e_sn:
                app.logger.error(f"Error creating ServiceNow ticket for {asset_id}: {e_sn}", exc_info=True)
                opsramp_connector.send_pcai_log(asset_id, "ERROR", f"Failed to create ServiceNow Work Order. Error: {e_sn}")
        else:
             app.logger.info(f"Skipping ServiceNow ticket for {asset_id}: Priority '{priority_level}', Confidence {confidence*100:.1f}% (Threshold: {confidence_threshold_sn*100:.1f}%). SN Connector usable: {bool(servicenow_connector and servicenow_connector.api_user)}")

        return jsonify({"status": "success", "message": f"LLM analysis processed for {asset_id}."}), 200

    except Exception as e:
        app.logger.error(f"Unhandled exception in /analyze_trigger for asset {asset_id}: {e}", exc_info=True)
        if opsramp_connector:
             opsramp_connector.send_pcai_log(asset_id, "CRITICAL_ERROR", f"Internal PCAI Agent error in analyze_trigger: {type(e).__name__}", {"error_details": str(e)})
        return jsonify({"status": "error", "message": "Internal server error during AI analysis"}), 500

@app.errorhandler(Exception) 
def handle_flask_error(e): # Renamed to avoid conflict if 'handle_exception' is used elsewhere
    app.logger.error(f"Unhandled Flask application error: {e}", exc_info=True)
    asset_id_err = "UnknownAssetFromFlaskError"
    try:
        if request and request.is_json:
            data = request.get_json(silent=True)
            if data and 'asset_id' in data:
                asset_id_err = data['asset_id']
    except RuntimeError: pass 
    if opsramp_connector:
        opsramp_connector.send_pcai_log(asset_id_err, "CRITICAL_ERROR", f"Unhandled PCAI Agent Flask error: {type(e).__name__}", {"error_details": str(e)})
    return jsonify(error=f"Flask App Error: {type(e).__name__} - {str(e)}", message="An internal server error occurred in Flask app."), 500

if __name__ == '__main__':
    app.logger.info(f"Attempting to start {APP_NAME}...")
    config_loaded = load_configuration()
    services_ready = False
    if config_loaded:
        services_ready = initialize_services()
    
    if not config_loaded or not services_ready:
        app.logger.critical("FATAL: Exiting due to configuration or service initialization failure.")
        # In a real script, you might sys.exit(1) here to prevent Flask from starting
    else:
        host = CONFIG.get('pcai_app', {}).get('listen_host', '0.0.0.0')
        port = int(CONFIG.get('pcai_app', {}).get('listen_port', 5000))
        
        llm_model_name_for_log = "N/A (Connector or Client not ready)"
        if llm_connector and llm_connector.client: 
            llm_model_name_for_log = llm_connector.model_name
        elif llm_connector: 
            llm_model_name_for_log = f"{llm_connector.model_name} (CLIENT INIT FAILED?)"
        
        app.logger.info(f"Starting {APP_NAME} Flask server on {host}:{port} (LLM: {llm_model_name_for_log})")
        # Note: Flask's 'debug=True' enables its own reloader and extensive Werkzeug logging.
        # The custom logger added above is more for application-level INFO/ERROR/DEBUG.
        app.run(host=host, port=port, debug=True, use_reloader=False)