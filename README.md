
# AI-Driven Predictive Maintenance Demo with HPE Technologies

## 1. Executive Summary

This project demonstrates an end-to-end AI-powered predictive maintenance solution for critical industrial machinery. It showcases the synergy of the HPE portfolio, including simulated components representing HPE Private Cloud AI (PCAI), HPE GreenLake, and OpsRamp, all underpinned by the comprehensive support of HPE Managed Services.

The core of this demonstration is an Agentic AI component, powered by a locally hosted Large Language Model (LLM via Ollama), that performs advanced diagnostics. The demo directly addresses the operational and financial impact of unplanned downtime by proactively identifying potential equipment failures, performing an AI-driven diagnosis, and automatically generating a maintenance ticket in ServiceNow. It also visualizes the real-time health of the asset using a ThingsBoard dashboard.

## 2. Architecture & Demo Flow

The demonstration follows a clear, event-driven flow:

1.  **IoT Sensor Simulator**: Generates and publishes real-time turbine sensor data (temperature, vibration, acoustics) via a local Mosquitto MQTT broker.
2.  **ThingsBoard**: A separate visualization platform that also subscribes to the MQTT data stream to provide a rich, real-time dashboard of the asset's health.
3.  **Edge Simulator**: Represents an edge device that subscribes to the MQTT data, detects gross anomalies based on pre-defined thresholds, and sends a trigger to the central AI.
4.  **PCAI Agent Application**: A Flask server that receives the trigger, uses Retrieval Augmented Generation (RAG) with a local LLM to perform a detailed diagnosis, and logs its findings.
5.  **ServiceNow**: If the AI's confidence is high, the PCAI agent makes a live API call to a ServiceNow instance to automatically create a prioritized incident ticket.

...

## 6. End-to-End Demo Flow Outline

This outlines the narrative flow of the live demonstration.

**Phase 1: Normal Operations**  
Begin by showing the ThingsBoard dashboard. All metrics for "Turbine #007" are green and stable, indicating normal operation.

**Phase 2: Anomaly Inception**  
An anomaly is discreetly injected. On the dashboard, vibration and/or acoustic graphs begin to show deviations, turning yellow or red. The Edge Simulator logs that it has detected an anomaly and is escalating it to the central AI.

**Phase 3: AI-Powered Diagnosis**  
The PCAI Agent logs show that it has received the trigger. It logs its "thought process" as it queries its knowledge base (technical manuals, repair logs) using RAG to understand the context of the sensor readings.

**Phase 4: Automated Remediation**  
The PCAI Agent logs its final diagnosis, confidence score, and recommended action. It then makes a live API call to ServiceNow, and a new, detailed incident ticket appears automatically in the ServiceNow UI.

**Phase 5: Closed-Loop Confirmation**  
Return to the dashboard, which is now updated to show a "Maintenance Scheduled" or "Critical Alert" status, confirming that the entire process from detection to action is complete and visualized.
