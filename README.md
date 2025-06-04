# AI-Driven Predictive Maintenance Demo with HPE Technologies

## 1. Executive Summary

This project demonstrates an end-to-end AI-powered predictive maintenance solution for critical industrial machinery. It showcases the synergy of the HPE portfolio, including HPE Private Cloud AI (PCAI), HPE GreenLake, OpsRamp, and Aruba networking (simulated), all underpinned by the comprehensive support of HPE Managed Services.

The demonstration directly addresses the substantial operational and financial impact of unplanned downtime and inefficient maintenance schedules in asset-heavy industries. It achieves this by proactively identifying potential equipment failures before they occur, transitioning operations from reactive to proactive and data-driven.

## 2. Key HPE Capabilities & Technologies Demonstrated

* **Simulated Edge AI (Aruba Networking Logic):** Initial data processing and anomaly flagging from IoT sensor data.
* **Central Agentic AI with RAG (HPE Private Cloud AI):** Advanced diagnostics and decision-making running live on HPE PCAI.
* **AIOps (HPE OpsRamp):** End-to-end monitoring, event correlation, and operational dashboards.
* **Cloud Platform (HPE GreenLake):** Underlying platform for service access and management.
* **Workflow Automation:** Seamless API integration with enterprise systems (simulated ServiceNow for work order generation).
* **Managed Services (HPE Managed Services):** Narrative highlighting the deployment, security, management, and optimization of the complex solution.

**Core Simulated/Third-Party Components:**
* **IoT Sensors & Machinery:** Simulated via Python scripts (e.g., Wind Turbine Gearbox).
* **ServiceNow:** Live developer instance for automated work order creation.
* **RAG Knowledge Base:** Simplified text files hosted locally for the PCAI RAG process.

## 3. Folder Structure
hpe_predictive_maintenance_demo/
├── .vscode/                  # VS Code specific settings
├── config/                   # Configuration files (e.g., demo_config.yaml)
├── data_simulators/          # Scripts for simulating IoT sensor data
│   └── iot_sensor_simulator.py
├── edge_logic/               # Scripts for simulated Aruba Edge processing logic
│   └── aruba_edge_simulator.py
├── knowledge_base_files/     # Text files for the RAG system
├── pcai_app/                 # Agentic AI application for HPE PCAI
├── utilities/                # Shared helper functions (optional)
├── .gitignore                # Specifies intentionally untracked files
├── README.md                 # This file
├── requirements.txt          # Python dependencies
└── main_demo_runner.py       # (Optional) Master script for local demo orchestration

## 4. Prerequisites

* **Python:** Version 3.8+
* **Git:** For cloning the repository.
* **HPE Private Cloud AI (PCAI) Kit:** Access for deploying the Agentic AI.
* **HPE OpsRamp Instance:** Access for AIOps dashboards and event ingestion.
* **ServiceNow Developer Instance:** For demonstrating automated work order creation.
* **HPE GreenLake Portal Access:** (As applicable for accessing services).
* **Required Python Packages:** Listed in `requirements.txt`.
* **API Keys/Endpoints:** For OpsRamp, ServiceNow, and the PCAI application (to be configured as per `config/demo_config.yaml.template` - *you'll create this template later*).

## 5. Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd hpe_predictive_maintenance_demo
    ```

2.  **Create and Activate a Python Virtual Environment:**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure the Demo:**
    * Copy the configuration template: `cp config/demo_config.yaml.template config/demo_config.yaml` (You will create `demo_config.yaml.template` later).
    * Edit `config/demo_config.yaml` to include your specific API endpoints, credentials (use environment variables or a secure vault for actual secrets in a real scenario), and other parameters.
    * Ensure the `knowledge_base_files/` are populated as per the demo requirements.

## 6. Running the Demo

*(This section will be updated as components are developed. Initially, it will focus on running the simulators.)*

The demo consists of several interconnected components:

1.  **Data Simulators (`data_simulators/iot_sensor_simulator.py`):**
    * Generates simulated sensor data (normal and anomalous) for a target asset (e.g., Turbine #007).
    * To run (example):
        ```bash
        python data_simulators/iot_sensor_simulator.py
        ```

2.  **Edge Logic (`edge_logic/aruba_edge_simulator.py`):**
    * Processes data from the sensor simulator.
    * Performs basic filtering and detects gross anomalies.
    * Sends metrics/events to OpsRamp (simulated API call initially).
    * Sends anomaly triggers to the PCAI Agent (simulated API call initially).
    * (Instructions on how this script ingests data from the sensor simulator will be added here - e.g., direct call, file-based, simple queue).

3.  **PCAI Agent Application (`pcai_app/`):**
    * Runs on the HPE PCAI Kit.
    * Receives triggers from the Edge Logic.
    * Performs advanced RAG-based diagnosis.
    * Sends diagnostic logs to OpsRamp.
    * Creates work orders in ServiceNow.
    * (Instructions on deploying and running this application on PCAI will be added).

4.  **OpsRamp Dashboard:**
    * Accessed via the HPE GreenLake portal.
    * Visualizes asset health, incoming alerts, AI diagnostic steps, and operational status.

5.  **ServiceNow Instance:**
    * Shows automatically generated work orders.

**Orchestration (Optional - for local development):**
* The `main_demo_runner.py` script might be used to start and coordinate local components for testing purposes.
    ```bash
    python main_demo_runner.py
    ```

## 7. End-to-End Demonstration Flow Outline

1.  **Phase 1: Setting the Scene - Normal Operations:** OpsRamp shows stable metrics for Turbine #007.
2.  **Phase 2: Anomaly Inception & Edge Intelligence:**
    * Demo operator triggers an anomaly in `iot_sensor_simulator.py`.
    * `aruba_edge_simulator.py` detects a deviation and sends alerts to OpsRamp & a trigger to PCAI.
3.  **Phase 3: Agentic AI Activation & RAG-Powered Diagnosis:**
    * The PCAI Agent (on HPE PCAI) receives the trigger.
    * It uses RAG with the `knowledge_base_files/` to diagnose the fault, logging its "thought process" to OpsRamp.
4.  **Phase 4: AI-Driven Insight & Automated Remediation:**
    * PCAI Agent determines the fault, severity, and recommended actions.
    * It autonomously creates a work order in the ServiceNow instance.
5.  **Phase 5: Closed-Loop Confirmation & Holistic AIOps View:**
    * OpsRamp shows the correlated events, from sensor anomaly to ServiceNow ticket, providing a unified view.
    * The narrative emphasizes the role of HPE Managed Services throughout.

## 8. Target Audience

* Technical Decision Makers (CTOs, VPs of IT/Engineering)
* IT/OT (Operational Technology) Managers
* Innovation Leaders and Digital Transformation Officers
* Attendees at events like HPE Discover, industry conferences, and strategic customer briefings.

## 9. Contributing

(Optional: Add guidelines if this were an open project for contributions.)

## 10. License

(Optional: Specify a license if applicable, e.g., MIT, Apache 2.0.)

---

This demonstration aims to provide compelling evidence of HPE's unique capability to deliver and manage sophisticated, end-to-end AI solutions that solve critical real-world customer challenges.