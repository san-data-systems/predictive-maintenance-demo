# pcai_app/api_connector.py

import json
import os
import requests # For actual HTTP calls
from requests.auth import HTTPBasicAuth # For ServiceNow Basic Auth
import ollama # Import the ollama client
import logging

from utilities import get_utc_timestamp # Use utility for timestamps

logger = logging.getLogger(__name__) # Standard Python logger for this module

class OpsRampConnector:
    """
    Simulates sending logs and updates to HPE OpsRamp.
    (Actual API calls to OpsRamp are not implemented in this version)
    """
    def __init__(self, opsramp_config: dict, pcai_agent_id: str):
        self.api_endpoint = opsramp_config.get("logs_endpoint", "SIMULATED_OPSRAMP_PCAI_LOGS_ENDPOINT_FALLBACK")
        self.pcai_agent_id = pcai_agent_id
        logger.info(f"OpsRampConnector initialized for {self.pcai_agent_id}. Endpoint (Simulated): {self.api_endpoint}")

    def send_pcai_log(self, asset_id: str, log_level: str, message: str, details: dict = None):
        log_payload = {
            "source_id": f"{self.pcai_agent_id}_{asset_id}", # e.g., PCAI_Agent_DemoCorp_DemoCorp_Turbine_007
            "timestamp": get_utc_timestamp(), 
            "log_level": log_level.upper(),
            "asset_id": asset_id,
            "message": message,
            "details": details or {}
        }
        print(f"\n--- SIMULATING OPSRAMP LOG ({log_level.upper()}) ---")
        print(f"To OpsRamp Endpoint: {self.api_endpoint}")
        print(f"Payload:\n{json.dumps(log_payload, indent=2)}")
        print(f"--- END OPSRAMP LOG ---")
        return {"status": "simulated_opsramp_log_success"}


class ServiceNowConnector:
    """
    Connects to ServiceNow to create incidents/work orders via REST API.
    """
    def __init__(self, servicenow_config: dict):
        self.instance_hostname = servicenow_config.get("instance_hostname")
        if not self.instance_hostname or "YOUR_INSTANCE_HOSTNAME" in self.instance_hostname:
            logger.critical("ServiceNow instance_hostname not configured correctly in config. ServiceNow integration will likely fail.")
            # Allow init, but calls will fail.
            self.api_user = None
            self.api_password = None
            self.api_base_url = None
            self.custom_fields_map = {}
            return

        self.api_user_env_var = servicenow_config.get("env_var_api_user", "SERVICENOW_API_USER")
        self.api_password_env_var = servicenow_config.get("env_var_api_password", "SERVICENOW_API_PASSWORD")
        
        self.api_user = os.environ.get(self.api_user_env_var)
        self.api_password = os.environ.get(self.api_password_env_var)

        if not self.api_user or not self.api_password:
            logger.warning( # Changed to warning to allow app to start, but log prominently
                f"ServiceNow API credentials not found in environment variables! "
                f"Ensure {self.api_user_env_var} and {self.api_password_env_var} are set. API calls will fail."
            )

        self.target_table = servicenow_config.get("target_table", "incident")
        self.api_base_url = f"https://{self.instance_hostname}/api/now/table/{self.target_table}"
        self.custom_fields_map = servicenow_config.get("custom_fields", {})

        logger.info(
            f"ServiceNowConnector initialized for instance: https://{self.instance_hostname}. "
            f"Target table: {self.target_table}. API User (from env var '{self.api_user_env_var}'): {'SET' if self.api_user else 'NOT SET'}."
        )

    def create_work_order(self, asset_id: str, short_description: str, description: str,
                          priority: str, assignment_group: str, recommended_parts: list,
                          ai_confidence: float = None, ai_reasoning: str = None, 
                          ai_recommended_actions: list = None) -> dict:
        if not self.api_user or not self.api_password:
            error_msg = "ServiceNow API credentials not configured. Cannot create ticket."
            logger.error(error_msg)
            return {"status": "error", "message": error_msg, "work_order_id": None}
        if not self.api_base_url: # If instance_hostname was bad
            error_msg = "ServiceNow instance hostname not configured. Cannot create ticket."
            logger.error(error_msg)
            return {"status": "error", "message": error_msg, "work_order_id": None}


        priority_map = {"HIGH": "1", "MEDIUM": "2", "LOW": "3"}
        sn_priority = priority_map.get(priority.upper(), "2")

        payload = {
            "short_description": short_description,
            "description": description,
            "priority": sn_priority,
            "assignment_group": {"display_value": assignment_group}, 
            "cmdb_ci": {"display_value": asset_id}, 
            "caller_id": self.api_user, 
            "contact_type": "Integration",
            "impact": sn_priority, 
            "urgency": sn_priority,
        }
        # Populate custom fields using the map from config
        if self.custom_fields_map.get("source_system"):
            payload[self.custom_fields_map["source_system"]] = "HPE PCAI Predictive Maintenance Agent"
        if ai_confidence is not None and self.custom_fields_map.get("ai_diagnosis_confidence"):
            payload[self.custom_fields_map["ai_diagnosis_confidence"]] = f"{ai_confidence*100:.1f}%"
        if ai_reasoning and self.custom_fields_map.get("ai_reasoning"):
            payload[self.custom_fields_map["ai_reasoning"]] = ai_reasoning
        if ai_recommended_actions and self.custom_fields_map.get("recommended_actions"):
            payload[self.custom_fields_map["recommended_actions"]] = "\n- ".join(ai_recommended_actions) 
        if recommended_parts and self.custom_fields_map.get("required_parts"):
             payload[self.custom_fields_map["required_parts"]] = ", ".join(recommended_parts if recommended_parts else ["N/A"])

        logger.info(f"Attempting to create ticket in ServiceNow: {short_description[:60]}...")
        # logger.debug(f"ServiceNow Payload: {json.dumps(payload, indent=2)}") # Be cautious with logging full payloads

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        response_summary = {"status": "error", "message": "Call not completed", "work_order_id": None}

        try:
            response = requests.post(
                self.api_base_url,
                auth=HTTPBasicAuth(self.api_user, self.api_password),
                headers=headers,
                json=payload,
                timeout=30 # Increased timeout for ServiceNow
            )
            logger.info(f"ServiceNow API raw response status: {response.status_code}")
            response.raise_for_status() 
            
            response_json = response.json()
            incident_number = response_json.get('result', {}).get('number', 'N/A')
            incident_sys_id = response_json.get('result', {}).get('sys_id', 'N/A')
            
            logger.info(f"Successfully created ticket in ServiceNow: {incident_number} (Sys ID: {incident_sys_id})")
            response_summary = {"status": "success", "work_order_id": incident_number, "sys_id": incident_sys_id}

        except requests.exceptions.HTTPError as e:
            error_details = f"HTTP Error: {e.response.status_code}. Response: {e.response.text[:500]}" # Log part of response
            logger.error(f"ServiceNow API call failed. {error_details}")
            response_summary = {"status": "error", "message": error_details, "work_order_id": None}
        except requests.exceptions.ConnectionError as e:
            error_details = f"Connection Error: {e}"
            logger.error(f"ServiceNow API call failed. {error_details}")
            response_summary = {"status": "error", "message": error_details, "work_order_id": None}
        except requests.exceptions.Timeout as e:
            error_details = f"Timeout Error: {e}"
            logger.error(f"ServiceNow API call failed. {error_details}")
            response_summary = {"status": "error", "message": error_details, "work_order_id": None}
        except requests.exceptions.RequestException as e:
            error_details = f"General Request Error: {e}"
            logger.error(f"ServiceNow API call failed. {error_details}")
            response_summary = {"status": "error", "message": error_details, "work_order_id": None}
        
        return response_summary


class OllamaConnector:
    def __init__(self, ollama_config: dict):
        self.model_name = ollama_config.get("model_name", "llama3:8b-instruct")
        self.api_base_url = ollama_config.get("api_base_url", "http://localhost:11434")
        self.request_timeout = int(ollama_config.get("request_timeout_seconds", 180))
        self.client = None # Initialize client to None
        
        try:
            self.client = ollama.Client(host=self.api_base_url, timeout=self.request_timeout)
            self.client.list() # Test connection
            logger.info(f"OllamaConnector initialized. Model: {self.model_name}, API Base: {self.api_base_url}. Connection successful.")
        except Exception as e:
            logger.error(f"Failed to initialize or connect Ollama client at {self.api_base_url}: {e}. Ensure Ollama server is running and model '{self.model_name}' is pulled.", exc_info=True)
            self.client = None # Explicitly set to None on failure

    def generate_structured_diagnosis(self, prompt: str) -> dict:
        if not self.client:
            logger.error("Ollama client not initialized. Cannot generate diagnosis.")
            return {"error": "Ollama client not initialized", "raw_output": ""}

        logger.info(f"Sending prompt to Ollama model: {self.model_name} (Prompt length: {len(prompt)} chars)")
        llm_output_str = ""
        try:
            response = self.client.generate(
                model=self.model_name,
                prompt=prompt,
                format="json", 
                options={"temperature": 0.2, "num_predict": 1024}
            )
            llm_output_str = response.get('response', '{}')
            logger.debug(f"Ollama raw JSON string response: {llm_output_str}")
            parsed_response = json.loads(llm_output_str)
            logger.info(f"Successfully parsed JSON response from Ollama.")
            return parsed_response
        except json.JSONDecodeError as e:
            logger.error(f"Ollama response was not valid JSON: {e}. Raw output (first 500 chars): '{llm_output_str[:500]}'")
            return {"error": "Failed to parse LLM JSON response", "raw_output": llm_output_str}
        except ollama.ResponseError as e:
            logger.error(f"Ollama API ResponseError: STATUS={e.status_code}, ERROR='{e.error}'. Model: {self.model_name}")
            return {"error": f"Ollama API ResponseError: {e.error}", "status_code": e.status_code, "raw_output": ""}
        except Exception as e:
            logger.error(f"Exception during Ollama API call: {e}", exc_info=True)
            return {"error": f"Ollama API call failed: {str(e)}", "raw_output": ""}