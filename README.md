
# AI-Driven Predictive Maintenance Demo with HPE Technologies

## 1. Executive Summary

This project demonstrates an end-to-end AI-powered predictive maintenance solution for critical industrial machinery. It showcases the synergy of the HPE portfolio, including HPE Private Cloud AI (PCAI), HPE GreenLake, and OpsRamp (simulated), all underpinned by the comprehensive support of HPE Managed Services.

The core of this demonstration is an Agentic AI component, powered by a locally hosted Large Language Model (LLM), that performs advanced diagnostics. The demo directly addresses the operational and financial impact of unplanned downtime by proactively identifying potential equipment failures, performing an AI-driven diagnosis, and automatically generating a real maintenance ticket in ServiceNow. It showcases a realistic transition from reactive to proactive, intelligence-driven operations.

## 2. Key Capabilities & Technologies Demonstrated

- **Simulated Edge Logic (ArubaEdgeSimulator)**: Initial data processing, anomaly flagging, and actual HTTP API calls to trigger the central AI.
- **Central Agentic AI (PcaiAgentApplication)**:
  - Hosted in a Flask application that listens for triggers.
  - Utilizes a locally hosted Large Language Model (e.g., Llama 3 via Ollama) for sophisticated reasoning, diagnosis, and recommendation generation.
  - Employs a simple Retrieval Augmented Generation (RAG) system to provide the LLM with relevant context from local knowledge base files.
- **AIOps (OpsRamp - Simulated)**: End-to-end monitoring, event correlation, and operational dashboards are simulated through console logs, showing how a platform like OpsRamp would provide holistic visibility.
- **Real Workflow Automation (ServiceNow)**: Seamless, live API integration with a real ServiceNow Developer Instance to autonomously create and populate incident tickets with AI-generated details.
- **Secure Credential Management**: Use of environment variables (and Kubernetes Secrets) to securely handle API credentials.
- **Cloud-Native Deployment**: A complete guide to containerizing the application with Docker and deploying it on a Kubernetes cluster with Kustomize.

## 3. Folder Structure

```
hpe_predictive_maintenance_demo/
├── config/
├── data_simulators/
├── edge_logic/
├── knowledge_base_files/
├── pcai_app/
├── utilities/
├── kubernetes/
│   ├── base/
│   └── overlays/
├── .gitignore
├── Dockerfile
├── Dockerfile.edge
├── main_demo_runner.py
├── README.md
└── requirements.txt
```

## 4. Prerequisites

### For Local Execution

- **Python**: Version 3.12+
- **Ollama**: Must be installed and running locally.
- **LLM Model**: A model must be pulled via Ollama (e.g., `llama3:8b`).

```bash
ollama pull llama3:8b
```

- **ServiceNow Developer Instance**
- **ServiceNow Credentials**

### For Kubernetes Deployment

- **All local execution prerequisites**
- **kubectl**
- **Kubernetes Cluster** with at least one NVIDIA GPU-enabled worker node
- **NVIDIA GPU Device Plugin**
- **Container Registry**
- **Docker**

## 5. Setup & Running the Demo (Locally)

### Clone the Repository

```bash
git clone <your-repository-url>
cd hpe_predictive_maintenance_demo
```

### Create and Activate Virtual Environment

```bash
python3.12 -m venv venv
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Set ServiceNow Environment Variables

**macOS/Linux**

```bash
export SERVICENOW_API_USER="your_sn_username"
export SERVICENOW_API_PASSWORD="your_sn_password"
```

**Windows**

```cmd
set SERVICENOW_API_USER="your_sn_username"
set SERVICENOW_API_PASSWORD="your_sn_password"
```

### Configure the Demo

Update `config/demo_config.yaml`.

### Run the Demo Runner

```bash
python3 main_demo_runner.py
```

## 6. Kubernetes Deployment Guide

### Step 1: Containerize the Applications

```bash
export REGISTRY_PATH="your-registry"

docker build -f Dockerfile -t ${REGISTRY_PATH}/pcai-app:latest .
docker push ${REGISTRY_PATH}/pcai-app:latest

docker build -f Dockerfile.edge -t ${REGISTRY_PATH}/edge-simulator-app:latest .
docker push ${REGISTRY_PATH}/edge-simulator-app:latest
```

### Step 2: Configure Kubernetes Manifests

Update image paths and config maps in relevant YAML files.

### Step 3: Deploy to Kubernetes

```bash
kubectl apply -f kubernetes/base/namespace.yaml

kubectl create secret generic pcai-app-credentials   --from-literal=SERVICENOW_API_USER='your_actual_sn_user'   --from-literal=SERVICENOW_API_PASSWORD='your_actual_sn_password'   -n pred-maint-demo

kubectl apply -k kubernetes/base/
```

### Step 4: Verify the Deployment

```bash
kubectl get pods -n pred-maint-demo -w
kubectl get svc -n pred-maint-demo
kubectl get pvc -n pred-maint-demo
```

### Step 5: Watch the Demo Flow & Logs

```bash
kubectl logs -f deployment/edge-simulator -n pred-maint-demo
kubectl logs -f deployment/pcai-app -n pred-maint-demo
kubectl logs -f deployment/ollama -n pred-maint-demo
```

### Step 6: Cleanup

```bash
kubectl delete -k kubernetes/base/
kubectl delete secret pcai-app-credentials -n pred-maint-demo
kubectl delete namespace pred-maint-demo
```

## 7. End-to-End Demo Flow Outline

- **Phase 1**: Normal Operations
- **Phase 2**: Anomaly Inception & Edge Intelligence
- **Phase 3**: Agentic AI Activation
- **Phase 4**: AI-Driven Insight & Remediation
- **Phase 5**: Closed-Loop Confirmation
