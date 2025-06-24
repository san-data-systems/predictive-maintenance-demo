# pcai_app/main_agent.py

from flask import Flask, request, jsonify
import os
import logging 
import threading

from utilities import get_utc_timestamp, get_full_config 

from utilities.api_connector import OpsRampConnector, ServiceNowConnector, OllamaConnector
from .rag_components import RAGSystem

CONFIG = {} 
APP_NAME = "PCAIAgentApplication_LLM_RealSN_Final"
app = Flask(__name__)
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true": 
    app.logger.setLevel(logging.DEBUG)
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
MAX_RAG_SNIPPETS_FOR_LLM_PROMPT = 3

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
            llm_connector = OllamaConnector(ollama_config=ollama_cfg)
            app.logger.info("OllamaConnector initialized. Connection will be attempted on first API call.")
        app.logger.info("PCAI Services initialization attempt complete.")
        return True
    except Exception as e:
        app.logger.critical(f"CRITICAL: Error initializing core connectors: {e}", exc_info=True)
        return False

def construct_llm_prompt(asset_id: str, live_sensor_data: dict, rag_snippets: list) -> str:
    sensor_data_summary = "\n".join([f"Asset ID: {asset_id}"] + [f"Timestamp of data: {live_sensor_data['timestamp']}"] + [
        f"Temperature: {live_sensor_data.get('temperature_c', 'N/A')}°C (Increase from baseline: {live_sensor_data.get('temperature_increase_c', 'N/A')}°C)"
    ] + [
        f"Overall Vibration: {live_sensor_data.get('vibration_overall_amplitude_g', 'N/A')}g @ {live_sensor_data.get('vibration_dominant_frequency_hz', 'N/A')}Hz"
    ] + [
        f"Specific Vibration Anomaly: {live_sensor_data.get('vibration_anomaly_signature_amp_g', 'N/A')}g at {live_sensor_data.get('vibration_anomaly_signature_freq_hz', 'N/A')}Hz" if live_sensor_data.get("vibration_anomaly_signature_freq_hz") else ""
    ] + [
        f"Acoustic Critical Band: {live_sensor_data.get('acoustic_critical_band_db', 'N/A')}dB"
    ])
    knowledge_base_context = "Relevant information from knowledge base (if any):\n"
    if rag_snippets and rag_snippets[0] != "No specific KB articles found matching the immediate query criteria.":
        for i, snippet in enumerate(rag_snippets):
            knowledge_base_context += f"KB{i+1}: {snippet}\n"
    else:
        knowledge_base_context += "No specific highly relevant articles were found by the RAG system for the immediate sensor readings and query.\n"
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
"""
    return prompt_template.format(sensor_data=sensor_data_summary, kb_context=knowledge_base_context)

def process_analysis_in_background(trigger_data):
    with app.app_context():
        asset_id = trigger_data.get("asset_id", "UnknownAssetOnPayload")
        live_sensor_data = trigger_data.get("full_sensor_data_at_trigger", {})
        app.logger.info(f"[BG Thread] Starting analysis for asset: {asset_id}")
        ai_thought_process = {"1_edge_trigger_summary": trigger_data.get("edge_detected_anomalies")}
        try:
            search_terms = ["failure", "maintenance", "vibration", "temperature", "acoustic", "GRX-II", asset_id]
            if live_sensor_data.get("vibration_anomaly_signature_freq_hz"):
                search_terms.append(f"{int(live_sensor_data['vibration_anomaly_signature_freq_hz'])}hz")
            rag_snippets_full = rag_system.query_knowledge_base(asset_id, live_sensor_data, list(set(search_terms)))
            rag_snippets_for_llm = rag_snippets_full[:MAX_RAG_SNIPPETS_FOR_LLM_PROMPT]
            ai_thought_process["2_rag_query_results"] = {"search_terms": list(set(search_terms)), "retrieved_snippets_count": len(rag_snippets_full), "top_snippets_for_llm": rag_snippets_for_llm}
            
            if llm_connector:
                llm_prompt = construct_llm_prompt(asset_id, live_sensor_data, rag_snippets_for_llm)
                llm_response_data = llm_connector.generate_structured_diagnosis(llm_prompt)
            else:
                llm_response_data = {
                  "diagnosis_summary": "TEST MODE: High-frequency vibration indicates bearing issue.",
                  "confidence_percentage": 95.0,
                  "reasoning": "This is a test case assuming no LLM is present.",
                  "recommended_actions": ["Manually inspect rear generator bearing."],
                  "required_parts": ["P/N G-5432"]
                }
            ai_thought_process["3_llm_diagnosis_response"] = llm_response_data

            final_diagnosis_summary, confidence, reasoning, recommended_actions, required_parts, priority_level = "LLM processing issue.", 0.0, "N/A", ["Manual inspection required."], ["N/A"], "LOW"
            if isinstance(llm_response_data, dict) and "error" not in llm_response_data:
                final_diagnosis_summary = llm_response_data.get("diagnosis_summary", final_diagnosis_summary)
                confidence_val = llm_response_data.get("confidence_percentage", 0.0)
                confidence = float(confidence_val) / 100.0 if isinstance(confidence_val, (int, float)) else 0.0
                reasoning = llm_response_data.get("reasoning", "No reasoning from LLM.")
                recommended_actions = llm_response_data.get("recommended_actions", [])
                required_parts = llm_response_data.get("required_parts", [])
                # --- MODIFICATION START ---
                # Adjusted priority thresholds for more impactful demo
                if confidence >= 0.8 or any(kw in final_diagnosis_summary.lower() for kw in ["critical", "severe", "urgent", "immediate", "failure"]): priority_level = "HIGH"
                elif confidence >= 0.6: priority_level = "MEDIUM"
                # --- MODIFICATION END ---
                app.logger.info(f"LLM Diagnosis: Summary='{final_diagnosis_summary}', Confidence={confidence*100:.1f}%, Priority={priority_level}")
            
            sn_config = CONFIG.get('pcai_app', {}).get('servicenow', {})
            confidence_threshold_sn = CONFIG.get('pcai_app', {}).get('diagnosis', {}).get('confidence_threshold_for_action', 0.70)
            
            if priority_level == "HIGH" and confidence >= confidence_threshold_sn and servicenow_connector.api_user:
                app.logger.info("ServiceNow conditions met. Initiating ServiceNow Work Order.")
                actions_str = "- " + "\n- ".join(recommended_actions)
                parts_str = ", ".join(required_parts if required_parts else ['N/A'])
                rag_context_for_sn = "".join([f"- {s[:150]}...\n" for s in rag_snippets_for_llm]) if rag_snippets_for_llm and rag_snippets_for_llm[0] != "No specific KB articles found matching the immediate query criteria." else "- No specific KB articles retrieved.\n"
                sn_description = f"""AI Diagnosis ({llm_connector.model_name if llm_connector else 'LLM'}):\n{final_diagnosis_summary}\n\nConfidence: {confidence*100:.1f}%\nAI Reasoning: {reasoning}\n\nRecommended Actions:\n{actions_str}\n\nPotentially Required Parts: {parts_str}\n\nKey RAG Snippets Considered by AI:\n{rag_context_for_sn}"""
                
                sn_response = servicenow_connector.create_work_order(
                    asset_id=asset_id,
                    short_description=f"AI DETECTED ({priority_level}): {final_diagnosis_summary[:80]} - {asset_id}",
                    description=sn_description, 
                    priority=priority_level,
                    assignment_group=sn_config.get('default_assignment_group', "DefaultGroup"),
                    recommended_parts=required_parts, 
                    ai_confidence=confidence, 
                    ai_reasoning=reasoning,
                    ai_recommended_actions=recommended_actions
                )
                ai_thought_process["4_automated_action_summary"] = {"action_taken": "Created ServiceNow Incident", "servicenow_response": sn_response}
            else:
                 ai_thought_process["4_automated_action_summary"] = {"action_taken": "None", "reason": f"Confidence {confidence*100:.1f}% or priority '{priority_level}' did not meet threshold."}
            
            # --- MODIFICATION START ---
            # This logic now maps priority level to a more meaningful OpsRamp log level
            final_log_level = "INFO" # Default
            if priority_level == "HIGH":
                final_log_level = "CRITICAL"
            elif priority_level == "MEDIUM":
                final_log_level = "WARN"
            # --- MODIFICATION END ---
            
            opsramp_connector.send_pcai_log(asset_id, final_log_level, f"AI Analysis Complete: {final_diagnosis_summary}", details=ai_thought_process)
            app.logger.info(f"Sent consolidated AI thought process to OpsRamp for asset: {asset_id}")

        except Exception as e:
            app.logger.error(f"[BG Thread] Unhandled exception during background analysis for asset {asset_id}: {e}", exc_info=True)
            ai_thought_process["error"] = f"Unhandled exception: {type(e).__name__} - {str(e)}"
            if opsramp_connector:
                opsramp_connector.send_pcai_log(asset_id, "CRITICAL_ERROR", "Internal PCAI Agent error during background analysis", details=ai_thought_process)

@app.route('/api/v1/analyze_trigger', methods=['POST'])
def analyze_trigger():
    trigger_data = request.get_json()
    if not trigger_data:
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400
    thread = threading.Thread(target=process_analysis_in_background, args=(trigger_data,))
    thread.daemon = True
    thread.start()
    app.logger.info("--- Sent 202 Accepted: AI analysis started in background ---")
    return jsonify({"status": "accepted", "message": "AI analysis has been started in the background."}), 202

@app.route('/healthz', methods=['GET'])
def health_check():
    """Simple health check endpoint for Kubernetes Liveness/Readiness Probes."""
    # A more advanced check could verify connections to downstream services.
    # For now, returning 200 OK if the app is running is a good start.
    return jsonify({"status": "healthy"}), 200

@app.errorhandler(Exception) 
def handle_flask_error(e):
    app.logger.error(f"Unhandled Flask application error: {e}", exc_info=True)
    if opsramp_connector:
        opsramp_connector.send_pcai_log("UnknownAssetFromFlaskError", "CRITICAL_ERROR", f"Unhandled PCAI Agent Flask error: {type(e).__name__}", {"error_details": str(e)})
    return jsonify(error=f"Flask App Error: {type(e).__name__} - {str(e)}", message="An internal server error occurred in Flask app."), 500

if __name__ == '__main__':
    app.logger.info(f"Attempting to start {APP_NAME}...")
    if not (load_configuration() and initialize_services()):
        app.logger.critical("FATAL: Exiting due to configuration or service initialization failure.")
    else:
        host = CONFIG.get('pcai_app', {}).get('listen_host', '0.0.0.0')
        port = int(CONFIG.get('pcai_app', {}).get('listen_port', 5000))
        llm_model_name_for_log = "N/A"
        if llm_connector: llm_model_name_for_log = llm_connector.model_name
        app.logger.info(f"Starting {APP_NAME} Flask server on {host}:{port} (LLM: {llm_model_name_for_log})")
        app.run(host=host, port=port, debug=True, use_reloader=False)