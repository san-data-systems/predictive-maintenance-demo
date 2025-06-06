# pcai_app/api_connector.py

import json
import os
import requests
from requests.auth import HTTPBasicAuth
import ollama
import logging

from utilities import get_utc_timestamp

logger = logging.getLogger(__name__)

class OpsRampConnector:
    """
    Connects to OpsRamp to send alerts (events/logs) via the actual REST API.
    Handles OAuth2 token acquisition and refresh.
    """
    def __init__(self, opsramp_config: dict, pcai_agent_id: str):
        self.pcai_agent_id = pcai_agent_id
        self.tenant_id = os.environ.get(opsramp_config.get("env_var_tenant_id"))
        self.api_key = os.environ.get(opsramp_config.get("env_var_api_key"))
        self.api_secret = os.environ.get(opsramp_config.get("env_var_api_secret"))
        self.api_hostname = opsramp_config.get("api_hostname")
        self.token_path = opsramp_config.get("token_endpoint_path")
        self.alert_path_template = opsramp_config.get("alert_endpoint_path")
        self.turbine_resource_id = opsramp_config.get("turbine_resource_id")
        self.access_token = None

        if not all([self.tenant_id, self.api_key, self.api_secret, self.api_hostname, self.turbine_resource_id]):
            logger.warning("OpsRamp config or credentials missing. OpsRamp integration will be disabled.")
            self.token_url, self.alert_url = None, None
        else:
            self.token_url = f"https://{self.api_hostname}{self.token_path}"
            self.alert_url = f"https://{self.api_hostname}{self.alert_path_template.format(tenantId=self.tenant_id)}"
            logger.info("OpsRampConnector initialized. Ready to get token and send alerts.")
            self.get_access_token()

    def get_access_token(self):
        if not self.token_url or not self.api_key or not self.api_secret:
            logger.error("Cannot get OpsRamp token, configuration or credentials missing.")
            return False
        logger.info(f"Requesting new OpsRamp access token...")
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        payload = {"grant_type": "client_credentials", "client_id": self.api_key, "client_secret": self.api_secret}
        try:
            response = requests.post(self.token_url, headers=headers, data=payload, timeout=15)
            response.raise_for_status()
            self.access_token = response.json().get("access_token")
            if self.access_token:
                logger.info("Successfully retrieved OpsRamp access token.")
                return True
            logger.error("Failed to retrieve OpsRamp access token.")
            self.access_token = None
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting OpsRamp access token: {e}", exc_info=True)
            self.access_token = None
            return False

    def send_pcai_log(self, asset_id: str, log_level: str, message: str, details: dict = None):
        if not self.alert_url or not self.access_token:
            logger.error("Cannot send OpsRamp alert: URL not configured or not authenticated.")
            return {"status": "error", "message": "Connector not ready"}

        priority_map = {"CRITICAL_ERROR": "P1", "ERROR": "P2", "WARN": "P3", "SUCCESS": "P5", "INFO": "P5"}
        subject_prefix_map = {"RAG_RESULT": "AI RAG Log", "SUCCESS": "AI Action Success", "ERROR": "AI Action Error", "CRITICAL_ERROR": "AI Agent Critical Error"}
        subject_prefix = subject_prefix_map.get(log_level.upper(), "AI Agent Log")
        
        if "LLM Diagnosis" in message:
            subject = f"AI Diagnosis ({asset_id}): {details.get('summary', 'Details in description')[:150]}"
        else:
            subject = f"{subject_prefix}: {message[:150]}"
            
        current_state = "OPEN" if log_level.upper() in ["ERROR", "WARN", "CRITICAL_ERROR"] else "OK"

        alert_object = {
            "resourceId": self.turbine_resource_id,
            "subject": subject,
            "currentState": current_state,
            "priority": priority_map.get(log_level.upper(), "P5"),
            # --- FINAL FIX: Set 'app' and 'serviceName' to expected values ---
            "app": "Custom",
            "serviceName": self.turbine_resource_id, # Using the unique resourceId is a robust way to identify the service
            "customFields": [
                {"name": "ai_agent_log_level", "value": log_level.upper()},
                {"name": "ai_agent_message", "value": message}
            ]
        }
        if details:
            for key, value in details.items():
                field_value = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
                alert_object["customFields"].append({"name": key, "value": field_value})
        
        payload = [alert_object]

        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "Accept": "application/json"}
        try:
            logger.info(f"Sending alert to OpsRamp with app '{alert_object['app']}': {subject}")
            response = requests.post(self.alert_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code in [200, 201, 202, 204]:
                logger.info(f"Successfully sent alert to OpsRamp. Status: {response.status_code}")
                return {"status": "success"}
            else:
                if response.status_code == 401:
                    logger.warning("OpsRamp token may have expired. Retrying after refresh.")
                    if self.get_access_token():
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        response = requests.post(self.alert_url, headers=headers, json=payload, timeout=15)
                        response.raise_for_status()
                        logger.info("Successfully sent alert to OpsRamp after token refresh.")
                        return {"status": "success"}
                response.raise_for_status()
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error sending alert to OpsRamp. Status: {e.response.status_code}, Body: {e.response.text[:500]}", exc_info=True)
            return {"status": "error", "message": f"HTTP Error: {e.response.status_code}"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending alert to OpsRamp: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

# --- The ServiceNowConnector and OllamaConnector classes below are unchanged ---
class ServiceNowConnector:
    def __init__(self, servicenow_config: dict):
        self.instance_hostname = servicenow_config.get("instance_hostname")
        if not self.instance_hostname or "YOUR_INSTANCE_HOSTNAME" in self.instance_hostname:
            logger.critical("ServiceNow instance_hostname not configured correctly. ServiceNow integration will likely fail.")
            self.api_user = None; return
        self.api_user_env_var = servicenow_config.get("env_var_api_user", "SERVICENOW_API_USER")
        self.api_password_env_var = servicenow_config.get("env_var_api_password", "SERVICENOW_API_PASSWORD")
        self.api_user, self.api_password = os.environ.get(self.api_user_env_var), os.environ.get(self.api_password_env_var)
        if not self.api_user or not self.api_password:
            logger.warning(f"ServiceNow API credentials not found in env vars. API calls will fail.")
        self.target_table = servicenow_config.get("target_table", "incident")
        self.api_base_url = f"https://{self.instance_hostname}/api/now/table/{self.target_table}"
        self.custom_fields_map = servicenow_config.get("custom_fields", {})
        logger.info(f"ServiceNowConnector initialized for instance: https://{self.instance_hostname}. API User: {'SET' if self.api_user else 'NOT SET'}.")

    def create_work_order(self, asset_id: str, short_description: str, description: str, priority: str, assignment_group: str, recommended_parts: list, ai_confidence: float = None, ai_reasoning: str = None, ai_recommended_actions: list = None) -> dict:
        if not self.api_user or not self.api_password:
            error_msg = "ServiceNow API credentials not configured. Cannot create ticket."; logger.error(error_msg)
            return {"status": "error", "message": error_msg, "work_order_id": None}
        priority_map = {"HIGH": "1", "MEDIUM": "2", "LOW": "3"}; sn_priority = priority_map.get(priority.upper(), "2")
        payload = {"short_description": short_description, "description": description, "priority": sn_priority, "assignment_group": {"display_value": assignment_group}, "cmdb_ci": {"display_value": asset_id}, "caller_id": self.api_user, "contact_type": "Integration", "impact": sn_priority, "urgency": sn_priority}
        if self.custom_fields_map.get("source_system"): payload[self.custom_fields_map["source_system"]] = "HPE PCAI Predictive Maintenance Agent"
        if ai_confidence is not None and self.custom_fields_map.get("ai_diagnosis_confidence"): payload[self.custom_fields_map["ai_diagnosis_confidence"]] = f"{ai_confidence*100:.1f}%"
        if ai_reasoning and self.custom_fields_map.get("ai_reasoning"): payload[self.custom_fields_map["ai_reasoning"]] = ai_reasoning
        if ai_recommended_actions and self.custom_fields_map.get("recommended_actions"): payload[self.custom_fields_map["recommended_actions"]] = "\n- ".join(ai_recommended_actions) 
        if recommended_parts and self.custom_fields_map.get("required_parts"): payload[self.custom_fields_map["required_parts"]] = ", ".join(recommended_parts if recommended_parts else ["N/A"])
        logger.info(f"Attempting to create ticket in ServiceNow: {short_description[:60]}..."); headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.post(self.api_base_url, auth=HTTPBasicAuth(self.api_user, self.api_password), headers=headers, json=payload, timeout=30)
            logger.info(f"ServiceNow API raw response status: {response.status_code}"); response.raise_for_status()
            response_json = response.json(); incident_number = response_json.get('result', {}).get('number', 'N/A'); incident_sys_id = response_json.get('result', {}).get('sys_id', 'N/A')
            logger.info(f"Successfully created ticket in ServiceNow: {incident_number} (Sys ID: {incident_sys_id})")
            return {"status": "success", "work_order_id": incident_number, "sys_id": incident_sys_id}
        except requests.exceptions.HTTPError as e:
            error_details = f"HTTP Error: {e.response.status_code} - {e.response.text[:500]}"; logger.error(f"ServiceNow API call failed. {error_details}")
            return {"status": "error", "message": error_details, "work_order_id": None}
        except requests.exceptions.RequestException as e:
            logger.error(f"ServiceNow API call failed: {e}", exc_info=True)
            return {"status": "error", "message": str(e), "work_order_id": None}


class OllamaConnector:
    def __init__(self, ollama_config: dict):
        self.model_name = ollama_config.get("model_name", "llama3:8b")
        self.api_base_url = ollama_config.get("api_base_url", "http://localhost:11434")
        self.request_timeout = int(ollama_config.get("request_timeout_seconds", 180))
        self.client = None
        try:
            self.client = ollama.Client(host=self.api_base_url, timeout=self.request_timeout)
            self.client.list(); logger.info(f"OllamaConnector initialized. Model: {self.model_name}, API Base: {self.api_base_url}. Connection successful.")
        except Exception as e:
            logger.error(f"Failed to initialize or connect Ollama client at {self.api_base_url}: {e}. Ensure Ollama server is running and model is pulled.", exc_info=True)
            self.client = None

    def generate_structured_diagnosis(self, prompt: str) -> dict:
        if not self.client:
            logger.error("Ollama client not initialized. Cannot generate diagnosis.")
            return {"error": "Ollama client not initialized", "raw_output": ""}
        logger.info(f"Sending prompt to Ollama model: {self.model_name} (Prompt length: {len(prompt)} chars)")
        llm_output_str = ""
        try:
            response = self.client.generate(model=self.model_name, prompt=prompt, format="json", options={"temperature": 0.2, "num_predict": 1024})
            llm_output_str = response.get('response', '{}')
            logger.debug(f"Ollama raw JSON string response: {llm_output_str}")
            parsed_response = json.loads(llm_output_str); logger.info("Successfully parsed JSON response from Ollama.")
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