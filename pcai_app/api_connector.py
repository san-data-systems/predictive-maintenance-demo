# pcai_app/api_connector.py

import json
import datetime
import time # For simulating unique IDs or delays

class OpsRampConnector:
    """
    Simulates sending logs and updates to HPE OpsRamp.
    """
    def __init__(self, opsramp_config: dict, pcai_agent_id: str):
        self.api_endpoint = opsramp_config.get("pcai_logs_endpoint", "SIMULATED_OPSRAMP_PCAI_LOGS_ENDPOINT")
        self.pcai_agent_id = pcai_agent_id # e.g., "PCAI_Agent_Turbine007"
        print(f"INFO: OpsRampConnector initialized for {self.pcai_agent_id}. Endpoint: {self.api_endpoint}")

    def send_pcai_log(self, asset_id: str, log_level: str, message: str, details: dict = None):
        """
        Simulates sending a structured log message from the PCAI agent to OpsRamp.
        log_level: e.g., "INFO", "WARN", "RAG_QUERY", "DIAGNOSIS"
        """
        log_payload = {
            "source_id": f"{self.pcai_agent_id}_{asset_id}", # Consistent with demo plan's event log
            "timestamp": datetime.datetime.utcnow().isoformat(timespec='milliseconds') + "Z",
            "log_level": log_level.upper(),
            "asset_id": asset_id,
            "message": message,
            "details": details or {}
        }
        print(f"\n--- SIMULATING OPSRAMP LOG ({log_level}) ---")
        print(f"To OpsRamp Endpoint: {self.api_endpoint}")
        print(f"Payload:\n{json.dumps(log_payload, indent=2)}")
        print(f"--- END OPSRAMP LOG ---")
        # In a real scenario:
        # requests.post(self.api_endpoint, json=log_payload)
        return {"status": "simulated_opsramp_log_success"}


class ServiceNowConnector:
    """
    Simulates creating work orders in ServiceNow.
    """
    def __init__(self, servicenow_config: dict):
        self.instance_url = servicenow_config.get("instance_url", "YOUR_SERVICENOW_INSTANCE.service-now.com")
        self.api_user = servicenow_config.get("api_user", "PCAI_API_USER")
        self.api_endpoint = f"https://{self.instance_url}/api/now/table/incident" # Example for incident, adjust for work_order
        # Password/token should be handled securely, e.g., environment variables
        self.api_password_placeholder = servicenow_config.get("api_password_placeholder", "SIMULATED_PASSWORD")
        print(f"INFO: ServiceNowConnector initialized for instance: {self.instance_url}")

    def create_work_order(self, asset_id: str, short_description: str, description: str,
                          priority: str, assignment_group: str, recommended_parts: list) -> dict:
        """
        Simulates creating a work order (or incident) in ServiceNow.
        Returns a dictionary with the simulated work order ID.
        """
        # Mapping priority string to ServiceNow integer values (example)
        priority_map = {"HIGH": "1", "MEDIUM": "2", "LOW": "3"}
        sn_priority = priority_map.get(priority.upper(), "2") # Default to Medium

        work_order_payload = {
            "short_description": short_description,
            "description": description,
            "priority": sn_priority,
            "assignment_group": {"display_value": assignment_group}, # Assuming lookup by name
            "cmdb_ci": {"display_value": asset_id}, # Link to Configuration Item
            "caller_id": self.api_user, # User creating the ticket
            "contact_type": "Integration",
            "impact": sn_priority, # Often impact and priority are related
            "urgency": sn_priority,
            # Custom fields might be needed for recommended_parts or AI source
            "u_recommended_parts": ", ".join(recommended_parts),
            "u_source_system": "HPE PCAI Predictive Maintenance Agent"
        }

        print(f"\n--- SIMULATING SERVICENOW WORK ORDER CREATION ---")
        print(f"To ServiceNow Endpoint: {self.api_endpoint}")
        print(f"User: {self.api_user}")
        print(f"Payload:\n{json.dumps(work_order_payload, indent=2)}")
        
        # Simulate a ServiceNow response
        simulated_work_order_id = f"WO{str(time.time_ns())[-7:]}" # Generate a unique-ish ID
        print(f"SUCCESS: Simulated Work Order '{simulated_work_order_id}' created in ServiceNow.")
        print(f"--- END SERVICENOW ---")
        
        # In a real scenario:
        # response = requests.post(
        #     self.api_endpoint,
        #     auth=(self.api_user, self.api_password_placeholder), # Use actual password/token
        #     json=work_order_payload,
        #     headers={"Content-Type": "application/json", "Accept": "application/json"}
        # )
        # response.raise_for_status()
        # return response.json().get('result', {}).get('sys_id', simulated_work_order_id)
        return {"status": "simulated_servicenow_wo_success", "work_order_id": simulated_work_order_id}