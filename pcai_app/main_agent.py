# pcai_app/main_agent.py

from flask import Flask, request, jsonify
import os
import logging 

from utilities import get_utc_timestamp, get_full_config 

from utilities.api_connector import OpsRampConnector, ServiceNowConnector, OllamaConnector
from .rag_components import RAGSystem

CONFIG = {} 
APP_NAME = "PCAIAgentApplication_LLM_RealSN_Final"

app = Flask(__name__)

# Configure Flask app logger to output to console for demo visibility
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true": 
    app.logger.setLevel(logging.DEBUG) # <--- CHANGE THIS TO logging.DEBUG
    if not any(isinstance(h, logging.StreamHandler) for h in app.logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
        ))
        app.logger.addHandler(handler)
    app.logger.propagate = False # Prevent duplicate logs in some environments

# Global instances for connectors and RAG system
opsramp_connector: OpsRampConnector = None
servicenow_connector: ServiceNowConnector = None
rag_system: RAGSystem = None
llm_connector: OllamaConnector = None 
pcai_agent_id_prefix: str = "PCAI_Agent_Default" # Default prefix, updated from config

MAX_RAG_SNIPPETS_FOR_LLM_PROMPT = 3 # Limits the number of RAG snippets sent to LLM for brevity/speed

def load_configuration():
    """Loads application configuration from common utilities."""
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
    """Initializes external service connectors (OpsRamp, ServiceNow, RAG, LLM)."""
    global opsramp_connector, servicenow_connector, rag_system, llm_connector
    app.logger.info("Attempting to initialize PCAI services...")
    if not CONFIG: 
        app.logger.error("Cannot initialize services: Global CONFIG is not loaded.")
        return False
        
    pcai_config = CONFIG.get('pcai_app', {})
    opsramp_cfg = pcai_config.get('opsramp', {})
    servicenow_cfg = pcai_config.get('servicenow', {})
    kb_path = pcai_config.get('knowledge_base_path', 'knowledge_base_files/')
    llm_provider_config = pcai_config.get('llm_config', {})
    ollama_cfg = llm_provider_config.get('ollama') if llm_provider_config.get('provider') == 'ollama' else None
    
    try:
        opsramp_connector = OpsRampConnector(opsramp_config=opsramp_cfg, pcai_agent_id=pcai_agent_id_prefix)
        servicenow_connector = ServiceNowConnector(servicenow_config=servicenow_cfg) 
        rag_system = RAGSystem(knowledge_base_path=kb_path)

        if not ollama_cfg:
            app.logger.warning("LLM (Ollama) configuration not found or provider not 'ollama'. LLM functionality will be disabled.")
            llm_connector = None
        else:
            # OllamaConnector is designed to connect lazily on first use, with retries
            llm_connector = OllamaConnector(ollama_config=ollama_cfg)
            app.logger.info("OllamaConnector initialized. Connection will be attempted on first API call.")

        app.logger.info("PCAI Services initialization attempt complete.")
        return True
        
    except Exception as e:
        app.logger.critical(f"CRITICAL: Error initializing core connectors: {e}", exc_info=True)
        return False

def construct_llm_prompt(asset_id: str, live_sensor_data: dict, rag_snippets: list) -> str:
    """
    Constructs the detailed prompt for the LLM based on sensor data and RAG context.
    """
    # Build a summary of current live sensor data for the LLM
    sensor_data_summary = "\n".join([f"Asset ID: {asset_id}"] + [f"Timestamp of data: {live_sensor_data['timestamp']}"] + [
        f"Temperature: {live_sensor_data.get('temperature_c', 'N/A')}°C (Increase from baseline: {live_sensor_data.get('temperature_increase_c', 'N/A')}°C)"
    ] + [
        f"Overall Vibration: {live_sensor_data.get('vibration_overall_amplitude_g', 'N/A')}g @ {live_sensor_data.get('vibration_dominant_frequency_hz', 'N/A')}Hz"
    ] + [
        f"Specific Vibration Anomaly: {live_sensor_data.get('vibration_anomaly_signature_amp_g', 'N/A')}g at {live_sensor_data.get('vibration_anomaly_signature_freq_hz', 'N/A')}Hz" if live_sensor_data.get("vibration_anomaly_signature_freq_hz") else ""
    ] + [
        f"Acoustic Critical Band: {live_sensor_data.get('acoustic_critical_band_db', 'N/A')}dB" # CORRECTED METRIC NAME
    ])

    # Format RAG snippets for inclusion in the prompt
    knowledge_base_context = "Relevant information from knowledge base (if any):\n"
    if rag_snippets and rag_snippets[0] != "No specific KB articles found matching the immediate query criteria.":
        for i, snippet in enumerate(rag_snippets):
            knowledge_base_context += f"KB{i+1}: {snippet}\n"
    else:
        knowledge_base_context += "No specific highly relevant articles were found by the RAG system for the immediate sensor readings and query.\n"

    # Define the LLM prompt template
    prompt_template = """You are an expert AI Predictive Maintenance diagnostician for industrial wind turbines, model GRX-II.
Your task is to analyze the provided live sensor data and contextual information from the knowledge base to diagnose potential faults.

Current Live Sensor Data:
{sensor_data}

{kb_context}
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
  "diagnosis_summary": "Probable early-stage gear tooth pitting detected.",
  "confidence_percentage": 92.5,
  "reasoning": "High-frequency vibration (121.38Hz) and a 5.5°C temperature increase directly correlate with KB01, which describes early-stage gear tooth pitting under similar conditions. This aligns with observed trends.",
  "recommended_actions": [
    "Schedule detailed inspection of the gearbox within 72 hours.",
    "Perform oil sample analysis for metal particles."
  ],
  "required_parts": ["P/N G-5432", "Gearbox Oil Type XYZ"]
}}

Now, generate ONLY the JSON output for the provided data:
"""
    # Format the template with actual data
    return prompt_template.format(sensor_data=sensor_data_summary, kb_context=knowledge_base_context)

@app.route('/api/v1/analyze_trigger', methods=['POST'])
def analyze_trigger():
    """
    Endpoint for the Edge Simulator to send anomaly triggers to the PCAI Agent.
    Triggers RAG, LLM analysis, and subsequent actions (OpsRamp, ServiceNow).
    """
    app.logger.info("--- DEBUG: Entered /api/v1/analyze_trigger endpoint ---")
    
    # Check if all critical services are initialized and available for this request
    # Rely on OllamaConnector's internal lazy connection for LLM
    services_ready_for_request = all([opsramp_connector, servicenow_connector, rag_system, llm_connector])
    if not services_ready_for_request:
        app.logger.error("DEBUG: One or more critical PCAI services are not ready. Cannot process request.")
        return jsonify({"status": "error", "message": "PCAI services not ready or LLM connection failed"}), 503
    app.logger.info("DEBUG: All PCAI services checked and appear OK for this request.")
    
    trigger_data = None 
    asset_id = "UnknownAssetInTrigger" # Default asset ID for logging if payload is bad
    
    try:
        trigger_data = request.get_json()
        if not trigger_data:
            app.logger.error("DEBUG: Invalid JSON payload from edge.")
            return jsonify({"status": "error", "message": "Invalid JSON payload from edge"}), 400
        
        app.logger.info(f"DEBUG: Successfully got JSON payload for trigger.")
        asset_id = trigger_data.get("asset_id", "UnknownAssetOnPayload")
        live_sensor_data = trigger_data.get("full_sensor_data_at_trigger", {})
        app.logger.info(f"DEBUG: Processing trigger for asset: {asset_id}")

        # Phase 3: AI Brain Activates - Send initial informational alert to OpsRamp
        app.logger.debug("DEBUG: Sending 'Received edge alert. Initiating AI analysis.' to OpsRamp.") # NEW DEBUG
        opsramp_connector.send_pcai_log(asset_id, "INFO", f"Received edge alert. Initiating AI analysis.", {"trigger_summary": trigger_data.get("edge_detected_anomalies")})
        app.logger.debug("DEBUG: Sent 'Received edge alert. Initiating AI analysis.' to OpsRamp.") # NEW DEBUG
        
        # Retrieval-Augmented (RA) Step - The AI "Does its Research"
        app.logger.info("DEBUG STEP 4: Before RAG query.")
        search_terms_for_rag = ["failure", "maintenance", "vibration", "temperature", "acoustic", "GRX-II", asset_id]
        if live_sensor_data.get("vibration_anomaly_signature_freq_hz"):
            # Add specific anomaly frequency to RAG search terms
            search_terms_for_rag.append(f"{int(live_sensor_data['vibration_anomaly_signature_freq_hz'])}hz")
        
        rag_snippets_full = rag_system.query_knowledge_base(asset_id, live_sensor_data, list(set(search_terms_for_rag)))
        rag_snippets_for_llm = rag_snippets_full[:MAX_RAG_SNIPPETS_FOR_LLM_PROMPT]
        app.logger.info(f"DEBUG STEP 5: After RAG query. Full snippets: {len(rag_snippets_full)}. Using top {len(rag_snippets_for_llm)} for LLM.")
        
        # Send RAG findings as informational alerts to OpsRamp
        app.logger.debug("DEBUG: Sending RAG snippets to OpsRamp.") # NEW DEBUG
        for idx, snippet in enumerate(rag_snippets_full): 
            opsramp_connector.send_pcai_log(asset_id, "INFO", f"RAG Snippet {idx+1}: '{snippet[:200]}...'")
        app.logger.debug("DEBUG: Sent RAG snippets to OpsRamp.") # NEW DEBUG
        
        # Generation (G) Step - The AI "Thinks and Writes its Report"
        app.logger.info("DEBUG STEP 6: Before constructing LLM prompt.")
        llm_prompt = construct_llm_prompt(asset_id, live_sensor_data, rag_snippets_for_llm)
        app.logger.info(f"DEBUG STEP 7: After constructing LLM prompt (length: {len(llm_prompt)}).")
        
        app.logger.debug("DEBUG: Sending 'Querying LLM...' to OpsRamp.") # NEW DEBUG
        opsramp_connector.send_pcai_log(asset_id, "INFO", f"Querying LLM ({llm_connector.model_name}) for diagnosis...")
        app.logger.debug("DEBUG: Sent 'Querying LLM...' to OpsRamp.") # NEW DEBUG

        app.logger.info("DEBUG STEP 8: PRE-CALL to llm_connector.generate_structured_diagnosis.")
        llm_response_data = llm_connector.generate_structured_diagnosis(llm_prompt) # This handles lazy connection/retries
        app.logger.info(f"DEBUG STEP 9: POST-CALL to llm_connector.generate_structured_diagnosis.")
        
        # Initialize default values in case of LLM error or missing fields
        final_diagnosis_summary, confidence, reasoning, recommended_action_details_list, parts_to_recommend = "LLM processing issue.", 0.0, "N/A", ["Manual inspection required."], ["N/A"]
        priority_level = "MEDIUM" # Default priority

        if isinstance(llm_response_data, dict) and "error" not in llm_response_data:
            app.logger.info(f"DEBUG: LLM Response Keys: {list(llm_response_data.keys())}")
            final_diagnosis_summary = llm_response_data.get("diagnosis_summary", final_diagnosis_summary)
            
            try:
                # Ensure confidence is correctly parsed as float for internal logic
                confidence_val = llm_response_data.get("confidence_percentage", 0.0)
                confidence = float(confidence_val) / 100.0 if isinstance(confidence_val, (int, float)) else 0.0
            except (ValueError, TypeError):
                app.logger.warning(f"Could not parse LLM confidence '{llm_response_data.get('confidence_percentage')}' to float.")
                confidence = 0.0 # Default to 0 if parsing fails
            
            reasoning = llm_response_data.get("reasoning", "No reasoning from LLM.")
            
            recommended_action_details_list = llm_response_data.get("recommended_actions", recommended_action_details_list)
            if not isinstance(recommended_action_details_list, list): 
                recommended_action_details_list = [str(recommended_action_details_list)] # Ensure it's a list

            parts_to_recommend = llm_response_data.get("required_parts", parts_to_recommend)
            if not isinstance(parts_to_recommend, list): 
                parts_to_recommend = [str(parts_to_recommend)] # Ensure it's a list
            
            # Determine priority based on confidence and diagnosis summary keywords
            if confidence > 0.75 or any(kw in final_diagnosis_summary.lower() for kw in ["critical", "severe", "urgent", "immediate", "failure"]):
                priority_level = "HIGH"
            elif confidence > 0.50: 
                priority_level = "MEDIUM"
            else: 
                priority_level = "LOW"
            
            app.logger.info(f"LLM Diagnosis: Summary='{final_diagnosis_summary}', Confidence={confidence*100:.1f}%, Priority={priority_level}")
            app.logger.debug("DEBUG: Sending LLM Reasoning to OpsRamp.") # NEW DEBUG
            opsramp_connector.send_pcai_log(asset_id, "INFO", f"LLM Reasoning: {reasoning}")
            app.logger.debug("DEBUG: Sent LLM Reasoning to OpsRamp.") # NEW DEBUG
        else:
            app.logger.error(f"LLM interaction error or malformed data. Response: {str(llm_response_data)[:1000]}")
            app.logger.debug("DEBUG: Sending LLM error alert to OpsRamp.") # NEW DEBUG
            opsramp_connector.send_pcai_log(asset_id, "ERROR", "LLM interaction failed or returned malformed data.", {"llm_error_response": str(llm_response_data)[:1000]})
            app.logger.debug("DEBUG: Sent LLM error alert to OpsRamp.") # NEW DEBUG
        
        # Send summary of LLM diagnosis to OpsRamp (this is a redundant call, already sent above)
        # opsramp_connector.send_pcai_log(asset_id, "WARN" if priority_level == "HIGH" else "INFO",
        #     f"LLM Diagnosis. Confidence: {confidence*100:.1f}%. Summary: {final_diagnosis_summary}",
        #     {"confidence": f"{confidence*100:.1f}%", "summary": final_diagnosis_summary, "llm_response_snippet": str(llm_response_data)[:200]})
        
        app.logger.debug("DEBUG: Sending LLM Recommended Actions summary to OpsRamp.") # NEW DEBUG
        opsramp_connector.send_pcai_log(asset_id, "INFO", f"LLM Recommended Actions: {'; '.join(recommended_action_details_list)}",
            {"actions": recommended_action_details_list, "parts": parts_to_recommend})
        app.logger.debug("DEBUG: Sent LLM Recommended Actions summary to OpsRamp.") # NEW DEBUG
        
        # Phase 4: Automated Action - Turning Insight into Work (ServiceNow)
        sn_config = CONFIG.get('pcai_app',{}).get('servicenow',{})
        diagnosis_cfg = CONFIG.get('pcai_app',{}).get('diagnosis',{})
        confidence_threshold_sn = diagnosis_cfg.get('confidence_threshold_for_action', 0.70) # Configurable threshold for SN ticket
        
        # Check conditions for ServiceNow ticket creation
        app.logger.debug(f"DEBUG: Checking ServiceNow ticket creation conditions: Priority={priority_level}, Confidence={confidence*100:.1f}% (Threshold={confidence_threshold_sn*100:.1f}%).") # NEW DEBUG
        if priority_level == "HIGH" and confidence >= confidence_threshold_sn and servicenow_connector and servicenow_connector.api_user:
            app.logger.debug("DEBUG: ServiceNow conditions met. Initiating ServiceNow Work Order.") # NEW DEBUG
            opsramp_connector.send_pcai_log(asset_id, "INFO", "Initiating ServiceNow Work Order (High Priority/Confidence).")
            try:
                # Format actions and parts for ServiceNow description
                actions_str = "- " + "\n- ".join(recommended_action_details_list)
                parts_str = ", ".join(parts_to_recommend if parts_to_recommend else ['N/A'])
                
                # Build RAG context string for ServiceNow description
                rag_context_for_sn = ""
                if rag_snippets_for_llm and rag_snippets_for_llm[0] != "No specific KB articles found matching the immediate query criteria.":
                    for rag_snip in rag_snippets_for_llm: # CORRECTED LOOP
                        rag_context_for_sn += f"- {rag_snip[:150]}...\n" # Add snippet summary
                else:
                    rag_context_for_sn += "- No specific KB articles retrieved or applicable for LLM input.\n"

                # Construct ServiceNow ticket description
                sn_description = f"""AI Diagnosis ({llm_connector.model_name if llm_connector else 'LLM'}):
{final_diagnosis_summary}

Confidence: {confidence*100:.1f}%
AI Reasoning: {reasoning}

Recommended Actions:
{actions_str}

Potentially Required Parts: {parts_str}

Key RAG Snippets Considered by AI (up to {MAX_RAG_SNIPPETS_FOR_LLM_PROMPT}):
{rag_context_for_sn}
"""
                app.logger.debug("DEBUG: Calling ServiceNowConnector to create work order.") # NEW DEBUG
                # Create ServiceNow work order
                sn_response = servicenow_connector.create_work_order(
                    asset_id=asset_id,
                    short_description=f"AI DETECTED ({priority_level}): {final_diagnosis_summary[:80]} - {asset_id}",
                    description=sn_description, 
                    priority=priority_level,
                    assignment_group=sn_config.get('default_assignment_group',"DefaultGroup"), # Use default group from config
                    recommended_parts=parts_to_recommend, 
                    ai_confidence=confidence, 
                    ai_reasoning=reasoning,
                    ai_recommended_actions=recommended_action_details_list 
                )
                work_order_id = sn_response.get("work_order_id", "N/A")
                app.logger.debug(f"DEBUG: ServiceNow response received: {sn_response.get('status')}. Work Order ID: {work_order_id}") # NEW DEBUG
                
                # Send confirmation alert to OpsRamp
                opsramp_connector.send_pcai_log(asset_id, "INFO", f"ServiceNow ticket creation response: {sn_response.get('status')}. Ticket: {work_order_id}", {"sn_response": sn_response})
                app.logger.debug("DEBUG: Sent ServiceNow confirmation to OpsRamp.") # NEW DEBUG
            
            except Exception as e_sn:
                app.logger.error(f"Error creating ServiceNow ticket for {asset_id}: {e_sn}", exc_info=True)
                app.logger.debug("DEBUG: Sending ServiceNow creation failure alert to OpsRamp.") # NEW DEBUG
                opsramp_connector.send_pcai_log(asset_id, "ERROR", f"Failed to create ServiceNow Work Order. Error: {e_sn}")
                app.logger.debug("DEBUG: Sent ServiceNow creation failure alert to OpsRamp.") # NEW DEBUG
            app.logger.debug("DEBUG: Finished ServiceNow interaction block.") # NEW DEBUG
        else:
            app.logger.info(f"Skipping ServiceNow ticket creation for {asset_id}: Priority '{priority_level}', Confidence {confidence*100:.1f}% (Threshold: {confidence_threshold_sn*100:.1f}%).")
            app.logger.debug("DEBUG: Skipped ServiceNow ticket creation based on conditions.") # NEW DEBUG
        
        app.logger.info("DEBUG: Returning JSON response from analyze_trigger.") # NEW DEBUG
        return jsonify({"status": "success", "message": f"LLM analysis processed for {asset_id}."}), 200
    
    except Exception as e:
        # General error handling for the endpoint
        app.logger.error(f"Unhandled exception in /analyze_trigger for asset {asset_id}: {e}", exc_info=True) 
        if opsramp_connector:
            # Send a critical error alert if an unhandled exception occurs
            opsramp_connector.send_pcai_log(asset_id, "CRITICAL_ERROR", f"Internal PCAI Agent error: {type(e).__name__}", {"error_details": str(e)})
        app.logger.debug("DEBUG: Returning error JSON response from analyze_trigger (unhandled exception).") # NEW DEBUG
        return jsonify({"status": "error", "message": "Internal server error during AI analysis"}), 500

@app.errorhandler(Exception) 
def handle_flask_error(e): 
    """Global Flask error handler to catch unhandled exceptions and log them."""
    app.logger.error(f"Unhandled Flask application error: {e}", exc_info=True)
    asset_id_err = "UnknownAssetFromFlaskError"
    try:
        if request and request.is_json:
            data = request.get_json(silent=True)
            if data and 'asset_id' in data:
                asset_id_err = data['asset_id']
    except RuntimeError: # Handle case where request context might not be available
        pass 
    if opsramp_connector:
        opsramp_connector.send_pcai_log(asset_id_err, "CRITICAL_ERROR", f"Unhandled PCAI Agent Flask error: {type(e).__name__}", {"error_details": str(e)})
    return jsonify(error=f"Flask App Error: {type(e).__name__} - {str(e)}", message="An internal server error occurred in Flask app."), 500

if __name__ == '__main__':
    app.logger.info(f"Attempting to start {APP_NAME}...")
    if not (load_configuration() and initialize_services()):
        app.logger.critical("FATAL: Exiting due to configuration or service initialization failure.")
    else:
        # Get listen host and port from config
        host = CONFIG.get('pcai_app', {}).get('listen_host', '0.0.0.0')
        port = int(CONFIG.get('pcai_app', {}).get('listen_port', 5000))
        
        # Log the LLM model name if available
        llm_model_name_for_log = "N/A"
        if llm_connector: # Only check if connector exists
            llm_model_name_for_log = llm_connector.model_name
        
        app.logger.info(f"Starting {APP_NAME} Flask server on {host}:{port} (LLM: {llm_model_name_for_log})")
        app.run(host=host, port=port, debug=True, use_reloader=False) # Start Flask app