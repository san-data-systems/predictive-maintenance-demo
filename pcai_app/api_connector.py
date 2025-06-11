# pcai_app/api_connector.py

import json
import os
import requests
from requests.auth import HTTPBasicAuth
import ollama
import logging
import time

from utilities import get_utc_timestamp

logger = logging.getLogger(__name__)

class OpsRampConnector:
    """
    Connects to OpsRamp to send alerts (events/logs) via the actual REST API.
    Handles OAuth2 token acquisition and refresh.
    """
    def __init__(self, opsramp_config: dict, pcai_agent_id: str):
        self.pcai_agent_id = pcai_agent_id
        
        # Get credentials from environment variables, using names from config
        self.tenant_id = os.environ.get(opsramp_config.get("env_var_tenant_id"))
        self.api_key = os.environ.get(opsramp_config.get("env_var_api_key"))
        self.api_secret = os.environ.get(opsramp_config.get("env_var_api_secret"))
        
        # Get URL components from config
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
        """Fetches an OAuth2 access token from OpsRamp."""
        if not self.token_url or not self.api_key or not self.api_secret:
            logger.error("Cannot get OpsRamp token, configuration or credentials missing.")
            self.access_token = None
            return False
            
        logger.info(f"Requesting new OpsRamp access token from {self.token_url}...")
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        payload = { "grant_type": "client_credentials", "client_id": self.api_key, "client_secret": self.api_secret }
        try:
            response = requests.post(self.token_url, headers=headers, data=payload, timeout=15)
            response.raise_for_status()
            self.access_token = response.json().get("access_token")
            if self.access_token:
                logger.info("Successfully retrieved OpsRamp access token.")
                return True
            else:
                logger.error("Failed to retrieve OpsRamp access token, 'access_token' key not in response.")
                self.access_token = None
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting OpsRamp access token: {e}", exc_info=True)
            self.access_token = None
            return False

    def send_pcai_log(self, asset_id: str, log_level: str, message: str, details: dict = None):
        """
        Formats and sends a log/event as an Alert to OpsRamp, using the correct
        'customFields' payload as an array of structured objects.
        """
        if not self.alert_url:
            logger.warning("OpsRamp alert URL not configured. Cannot send alert.")
            return {"status": "error", "message": "Configuration error"}

        if not self.access_token:
            logger.warning("No OpsRamp access token available. Attempting to refresh...")
            if not self.get_access_token():
                logger.error("Failed to refresh OpsRamp token. Aborting send.")
                return {"status": "error", "message": "Authentication failed"}

        log_level_upper = log_level.upper()
        priority_map = {"CRITICAL": "P1", "ERROR": "P2", "WARN": "P3", "INFO": "P5", "SUCCESS": "P5"}
        state_map = {"CRITICAL": "CRITICAL", "ERROR": "CRITICAL", "WARN": "WARNING", "INFO": "OK", "SUCCESS": "OK"}
        
        timestamp_for_subject = get_utc_timestamp()
        subject = f"AI Agent Log ({log_level_upper}): {message[:120]} - {timestamp_for_subject}"

        # --- FINAL FIX: Create a 'customFields' list of OBJECTS with name/value pairs ---
        custom_fields_list = []
        if details:
            for key, value in details.items():
                # Ensure the value is a simple string for the 'value' field
                if isinstance(value, list):
                    value_str = ", ".join(map(str, value))
                elif isinstance(value, dict):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)
                
                # Create the object with 'name' and 'value' keys and append it to the list
                custom_fields_list.append({
                    "name": key,
                    "value": value_str
                })
        # --- END OF FIX ---
        
        description = f"{message}\n\nSee custom fields for detailed diagnostic data."

        alert_object = {
            "subject": subject,
            "currentState": state_map.get(log_level_upper, "OK"),
            "priority": priority_map.get(log_level_upper, "P5"),
            "description": description,
            "customFields": custom_fields_list,
            "device": {
                "resourceUUID": self.turbine_resource_id
            },
            "app": "Custom",
            "serviceName": asset_id
        }
        
        payload = [alert_object]
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json", "Accept": "application/json"}
        
        try:
            logger.info(f"Sending alert to OpsRamp with payload: {json.dumps(payload)}")
            response = requests.post(self.alert_url, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            logger.info(f"Successfully sent alert to OpsRamp. Status: {response.status_code}")
            return {"status": "success"}
        except requests.exceptions.HTTPError as e:
            logger.error(f"Error sending alert to OpsRamp. Status: {e.response.status_code}, Body: {e.response.text[:500]}", exc_info=True)
            return {"status": "error", "message": f"HTTP Error: {e.response.status_code}"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending alert to OpsRamp: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}


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
            logger.warning(f"ServiceNow API credentials not found in env vars: {self.api_user_env_var}, {self.api_password_env_var}. API calls will fail.")
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
    """
    Connects to an Ollama server to perform LLM-based diagnosis.
    Includes a retry mechanism to handle slow-starting dependencies.
    """
    def __init__(self, ollama_config: dict):
        self.model_name = ollama_config.get("model_name", "llama3:8b")
        self.api_base_url = ollama_config.get("api_base_url", "http://localhost:11434")
        self.request_timeout = int(ollama_config.get("request_timeout_seconds", 180))
        
        self.client = None
        self.max_retries = 5
        self.retry_delay_seconds = 15
        logger.info(f"OllamaConnector configured for model '{self.model_name}'. Connection will be established on first use.")

    def _get_client(self):
        """
        Gets a connected Ollama client, retrying if necessary.
        This makes the connection lazy and resilient.
        """
        if self.client:
            try:
                self.client.list()
                return self.client
            except Exception:
                logger.warning("Existing Ollama client connection lost. Attempting to reconnect.")
                self.client = None

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Attempting to connect to Ollama at {self.api_base_url} (Attempt {attempt + 1}/{self.max_retries})...")
                client_instance = ollama.Client(host=self.api_base_url, timeout=self.request_timeout)
                client_instance.list()
                logger.info("Successfully connected to Ollama.")
                self.client = client_instance
                return self.client
            except Exception as e:
                logger.warning(f"Ollama connection attempt failed: {e}")
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {self.retry_delay_seconds} seconds...")
                    time.sleep(self.retry_delay_seconds)
                else:
                    logger.error("All retry attempts to connect to Ollama have failed.")
                    return None
        return None

    def generate_structured_diagnosis(self, prompt: str) -> dict:
        client = self._get_client()
        if not client:
            logger.error("Ollama client not available. Cannot generate diagnosis.")
            return {"error": "Ollama client not available", "raw_output": ""}
        
        logger.info(f"Sending prompt to Ollama model: {self.model_name} (Prompt length: {len(prompt)} chars)")
        llm_output_str = ""
        try:
            response = client.generate(model=self.model_name, prompt=prompt, format="json", options={"temperature": 0.2, "num_predict": 1024})
            llm_output_str = response.get('response', '{}')
            logger.debug(f"Ollama raw JSON string response: {llm_output_str}")
            parsed_response = json.loads(llm_output_str)
            logger.info("Successfully parsed JSON response from Ollama.")
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