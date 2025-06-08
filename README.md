
# AI-Driven Predictive Maintenance Demo with HPE Technologies

## 1. Executive Summary
This project demonstrates an end-to-end AI-powered predictive maintenance solution for critical industrial machinery. It showcases a modern, decoupled IoT architecture using MQTT for data streaming, with an Agentic AI component performing advanced diagnostics and triggering real-world actions.

The demo directly addresses the operational and financial impact of unplanned downtime by proactively identifying potential equipment failures. It features an IoT sensor publishing data, an edge component subscribing to and analyzing that data, and a central AI brain that uses a local LLM (via Ollama) and Retrieval Augmented Generation (RAG) to diagnose faults and automatically create tickets in ServiceNow and alerts in OpsRamp.

## 2. Key Capabilities & Technologies Demonstrated

**Decoupled IoT Architecture**  
A realistic data pipeline using an MQTT Broker (Eclipse Mosquitto) to decouple the IoT sensor from the edge application.

**Simulated Edge Logic**  
An MQTT subscriber (ArubaEdgeSimulator) that processes live data streams, flags anomalies, and makes real API calls to trigger the central AI.

**Central Agentic AI (PcaiAgentApplication)**

- A Flask application that listens for triggers from the edge.
- Utilizes a locally hosted Large Language Model (e.g., Llama 3 via Ollama) for sophisticated reasoning and diagnosis.
- Employs a simple RAG system to provide the LLM with relevant context from a knowledge base.

**Real API Integrations**

- **OpsRamp**: Sends real-time alerts and AI log data to a configured OpsRamp tenant for monitoring and visualization.
- **ServiceNow**: Autonomously creates and populates detailed incident tickets in a real ServiceNow instance.

**Secure Credential Management**  
Uses environment variables and Kubernetes Secrets to securely handle API credentials.

**Cloud-Native Deployment**  
A complete guide to containerizing all components with Docker and deploying them on a Kubernetes cluster using Kustomize.

## 3. Folder Structure
```plaintext
hpe_predictive_maintenance_demo/
├── config/
│   └── demo_config.yaml
├── data_simulators/
│   └── iot_sensor_simulator.py
├── edge_logic/
│   └── aruba_edge_simulator.py
├── knowledge_base_files/
│   ├── ... (text files)
├── pcai_app/
│   ├── ... (python files)
├── utilities/
│   └── ... (python files)
├── kubernetes/
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── mqtt-broker-configmap.yaml
│   │   ├── mqtt-broker-deployment.yaml
│   │   ├── mqtt-broker-service.yaml
│   │   ├── iot-sensor-deployment.yaml
│   │   ├── ... (other deployment and service files)
│   └── overlays/
│       └── development/
│           └── kustomization.yaml
├── .gitignore
├── Dockerfile                # For the 'pcai_app'
├── Dockerfile.edge           # For the 'edge_simulator_app'
├── Dockerfile.sensor         # For the 'iot_sensor_app'
├── main_demo_runner.py       # (OBSOLETE) For previous direct-call architecture
├── README.md                 # This file
└── requirements.txt
```

## 4. Prerequisites

### For Local Execution
- **Python**: Version 3.12+
- **Docker Desktop**: Required to run the Mosquitto MQTT broker locally.
- **Ollama**: Must be installed and running locally. [Ollama Website](https://ollama.com)
- **LLM Model**: A model must be pulled via Ollama (e.g., llama3:8b):
```bash
ollama pull llama3:8b
```
- **ServiceNow & OpsRamp Credentials**: API credentials for both your ServiceNow PDI and your OpsRamp tenant.

### For Kubernetes Deployment
- All local prerequisites (for building/testing).
- `kubectl`: The Kubernetes command-line tool.
- **Kubernetes Cluster**: With at least one NVIDIA GPU-enabled worker node and the NVIDIA device plugin installed.
- **Container Registry**: Access to a registry (Docker Hub, GCR, etc.) to push your images.

## 5. Setup & Running the Demo (Locally)

### Step 1: Set Environment Variables
```bash
# Activate virtual environment
source venv/bin/activate

# Set ServiceNow Credentials
export SERVICENOW_API_USER="your_sn_username"
export SERVICENOW_API_PASSWORD="your_sn_password"

# Set OpsRamp Credentials
export OPSRAMP_TENANT_ID="your_opsramp_tenant_id"
export OPSRAMP_API_KEY="your_opsramp_api_key"
export OPSRAMP_API_SECRET="your_opsramp_api_secret"
```

### Step 2: Configure and Run Components
Ensure your `config/demo_config.yaml` is updated with your ServiceNow hostname and OpsRamp Resource ID.

#### Terminal 1: Start MQTT Broker
```bash
docker run -it --rm -p 1883:1883 \
-v $(pwd)/config/mosquitto.conf:/mosquitto/config/mosquitto.conf \
eclipse-mosquitto
```

#### Terminal 2: Start PCAI Agent App
```bash
python3 -m pcai_app.main_agent
```

#### Terminal 3: Start Edge Simulator (Subscriber)
```bash
source venv/bin/activate
python3 -m edge_logic.aruba_edge_simulator
```

#### Terminal 4: Start IoT Sensor (Publisher)
```bash
source venv/bin/activate
python3 -m data_simulators.iot_sensor_simulator
```

## 6. Kubernetes Deployment Guide

### Step 1: Containerize All Applications
```bash
export REGISTRY_PATH="your-registry"

# Build and push PCAI App
docker build -f Dockerfile -t ${REGISTRY_PATH}/pcai-app:latest .
docker push ${REGISTRY_PATH}/pcai-app:latest

# Build and push Edge Simulator
docker build -f Dockerfile.edge -t ${REGISTRY_PATH}/edge-simulator-app:latest .
docker push ${REGISTRY_PATH}/edge-simulator-app:latest

# Build and push IoT Sensor
docker build -f Dockerfile.sensor -t ${REGISTRY_PATH}/iot-sensor-app:latest .
docker push ${REGISTRY_PATH}/iot-sensor-app:latest
```

### Step 2: Configure Kubernetes Manifests
- Update image paths in deployment files.
- Update `pcai-app-configmap.yaml` with ServiceNow and OpsRamp details.

### Step 3: Deploy to Kubernetes
```bash
kubectl apply -f kubernetes/base/namespace.yaml

# Create Secrets
kubectl create secret generic pcai-app-credentials \
  --from-literal=SERVICENOW_API_USER='your_sn_user' \
  --from-literal=SERVICENOW_API_PASSWORD='your_sn_password' \
  -n pred-maint-demo

kubectl create secret generic opsramp-credentials \
  --from-literal=OPSRAMP_TENANT_ID='your_opsramp_tenant_id' \
  --from-literal=OPSRAMP_API_KEY='your_opsramp_api_key' \
  --from-literal=OPSRAMP_API_SECRET='your_opsramp_api_secret' \
  -n pred-maint-demo

# Apply the stack
kubectl apply -k kubernetes/base/
```

### Step 4: Verify and Watch the Demo
```bash
kubectl get pods -n pred-maint-demo -w
```
Tail logs of all components to observe workflow.

### Step 5: Cleanup
```bash
kubectl delete -k kubernetes/base/
kubectl delete secret pcai-app-credentials opsramp-credentials -n pred-maint-demo
kubectl delete namespace pred-maint-demo
```