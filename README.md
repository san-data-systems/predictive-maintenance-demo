# AI-Driven Predictive Maintenance Demo with HPE Technologies

## 1. Executive Summary

This project demonstrates an end-to-end AI-powered predictive maintenance solution for critical industrial machinery. It showcases the synergy of the HPE portfolio, including HPE Private Cloud AI (PCAI), HPE GreenLake, and OpsRamp (simulated), all underpinned by the comprehensive support of HPE Managed Services.

The core of this demonstration is an **Agentic AI component, powered by a locally hosted Large Language Model (LLM)**, that performs advanced diagnostics. The demo directly addresses the operational and financial impact of unplanned downtime by proactively identifying potential equipment failures, performing an AI-driven diagnosis, and automatically generating a real maintenance ticket in ServiceNow. It showcases a realistic transition from reactive to proactive, intelligence-driven operations.

## 2. Key Capabilities & Technologies Demonstrated

* **Simulated Edge Logic (`ArubaEdgeSimulator`):** Initial data processing, anomaly flagging, and **actual HTTP API calls** to trigger the central AI.
* **Central Agentic AI (`PcaiAgentApplication`):**
    * Hosted in a Flask application that listens for triggers.
    * Utilizes a **locally hosted Large Language Model (e.g., Llama 3 via Ollama)** for sophisticated reasoning, diagnosis, and recommendation generation.
    * Employs a simple Retrieval Augmented Generation (RAG) system to provide the LLM with relevant context from local knowledge base files.
* **AIOps (OpsRamp - Simulated):** End-to-end monitoring, event correlation, and operational dashboards are simulated through console logs, showing how a platform like OpsRamp would provide holistic visibility.
* **Real Workflow Automation (ServiceNow):** Seamless, live API integration with a **real ServiceNow Developer Instance** to autonomously create and populate incident tickets with AI-generated details.
* **Secure Credential Management:** Use of **environment variables** to securely handle API credentials for ServiceNow.

## 3. Folder Structure

hpe_predictive_maintenance_demo/
├── config/                   # Configuration files (e.g., demo_config.yaml)
├── data_simulators/          # Scripts for simulating IoT sensor data
├── edge_logic/               # Scripts for simulated Aruba Edge processing logic
├── knowledge_base_files/     # Text files for the RAG system
├── pcai_app/                 # Agentic AI application (Flask, LLM, RAG, Connectors)
├── utilities/                # Shared helper functions (config loading, etc.)
├── .gitignore                # Specifies intentionally untracked files
├── Dockerfile                # Example Dockerfile for pcai_app
├── Dockerfile.edge           # Example Dockerfile for edge_simulator_app
├── main_demo_runner.py       # Master script to orchestrate the local demo
├── README.md                 # This file
└── requirements.txt          # Python dependencies

## 4. Prerequisites

* **Python:** Version 3.9+
* **Git:** For cloning the repository.
* **Ollama:** Must be installed and running on your local machine to serve the LLM. [Ollama Website](https://ollama.com/)
* **LLM Model:** A model must be pulled via Ollama (e.g., `llama3:8b`).
    ```bash
    ollama pull llama3:8b
    ```
* **ServiceNow Developer Instance:** An active Personal Developer Instance (PDI) is required. [ServiceNow Developer Program](https://developer.servicenow.com/)
* **ServiceNow Credentials:** You need the username and password for an API-enabled user on your ServiceNow PDI.
* **Required Python Packages:** Listed in `requirements.txt` (e.g., `Flask`, `PyYAML`, `ollama`, `requests`).
* **Environment Variables:** You MUST set environment variables for your ServiceNow credentials.

## 5. Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd hpe_predictive_maintenance_demo
    ```

2.  **Create and Activate a Python Virtual Environment:**
    ```bash
    python3 -m venv venv
    # On Windows
    # venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set Up Ollama:**
    * Install Ollama from its official website.
    * Pull the LLM model specified in `config/demo_config.yaml` (default is now updated to `llama3:8b`).
        ```bash
        ollama pull llama3:8b
        ```
    * Ensure the Ollama server is running. (It usually starts automatically as a background service after the first run).

5.  **Set ServiceNow Environment Variables:**
    * In the terminal you will use to run the demo, set the following environment variables.
    * **On macOS/Linux:**
        ```bash
        export SERVICENOW_API_USER="your_sn_username"
        export SERVICENOW_API_PASSWORD="your_sn_password"
        ```
    * **On Windows (Command Prompt):**
        ```bash
        set SERVICENOW_API_USER="your_sn_username"
        set SERVICENOW_API_PASSWORD="your_sn_password"
        ```

6.  **Configure the Demo:**
    * **`config/demo_config.yaml`**: Open this file.
        * Update the `pcai_app.servicenow.instance_hostname` with your ServiceNow PDI hostname (e.g., `dev12345.service-now.com`).
        * Ensure `pcai_app.llm_config.ollama.model_name` is set to `llama3:8b`.
    * **ServiceNow Instance Setup:** Log into your ServiceNow PDI and perform the required setup (creating an API user with correct roles, adding the recommended custom fields to the Incident form, etc.). This is crucial for the API calls to succeed and for the demo to be visually compelling.

## 6. Running the Demo

The `main_demo_runner.py` script orchestrates the local execution of all components.

1.  Ensure your **Ollama server is running**.
2.  Ensure your **ServiceNow environment variables are set** in your terminal.
3.  Ensure your **Python virtual environment is activated**.
4.  From the project root directory, run the script:
    ```bash
    python3 main_demo_runner.py
    ```

**Expected Behavior:**
* The script will first launch the `pcai_app` (Flask server).
* After a short delay, it will launch the `edge_simulator_app`.
* The console will show interleaved logs from both processes.
* As the simulation runs, the edge simulator will eventually detect an anomaly and send a **real HTTP trigger** to the PCAI app.
* The PCAI app will then process the trigger, perform a RAG query, make a **real API call to your local Ollama LLM**, parse the diagnosis, and then make a **real API call to your ServiceNow PDI** to create an incident.
* You can watch the logs to see this entire flow and then check your ServiceNow instance for the newly created incident.
* Press **`Ctrl+C`** in the terminal to stop all demo components.

## 7. End-to-End Demonstration Flow Outline

1.  **Phase 1: Setting the Scene - Normal Operations:** The Edge Simulator logs show stable metrics for Turbine #007.
2.  **Phase 2: Anomaly Inception & Edge Intelligence:** The sensor simulator injects an anomaly. The Edge Simulator detects it and sends a real HTTP trigger to the PCAI Application.
3.  **Phase 3: Agentic AI Activation & Diagnosis:**
    * The PCAI Application receives the trigger.
    * It performs a RAG query on its knowledge base to gather context.
    * It constructs a detailed prompt with sensor data and RAG context and sends it to the **locally hosted LLM via Ollama**.
4.  **Phase 4: AI-Driven Insight & Automated Remediation:**
    * The LLM **reasons** over the provided data and generates a structured JSON response containing the diagnosis, confidence, and recommended actions.
    * The PCAI Application parses this response and autonomously creates a detailed, prioritized incident ticket in your **real ServiceNow instance** via a live API call.
5.  **Phase 5: Closed-Loop Confirmation & Holistic AIOps View:**
    * The demo concludes by showing the AI-generated ticket in the ServiceNow UI.
    * The console logs represent what an AIOps platform like OpsRamp would display: a complete, correlated story from sensor anomaly to automated remediation, enabling a proactive operational model.

## 8. Target Audience

* Technical Decision Makers (CTOs, VPs of IT/Engineering)
* IT/OT (Operational Technology) Managers
* Innovation Leaders and Digital Transformation Officers
* Attendees at events like HPE Discover, industry conferences, and strategic customer briefings.