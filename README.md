
# AI-Driven Predictive Maintenance Demo with HPE Technologies

## 1. Executive Summary

This project demonstrates an end-to-end AI-powered predictive maintenance solution for critical industrial machinery. It showcases the synergy of the HPE portfolio, including simulated components representing HPE Private Cloud AI (PCAI), HPE GreenLake, and OpsRamp, all underpinned by the comprehensive support of HPE Managed Services.

The core of this demonstration is an Agentic AI component, powered by a locally hosted Large Language Model (LLM via Ollama), that performs advanced diagnostics. The demo directly addresses the operational and financial impact of unplanned downtime by proactively identifying potential equipment failures, performing an AI-driven diagnosis, and automatically generating a maintenance ticket in ServiceNow. It also visualizes the real-time health of the asset using a ThingsBoard dashboard.

## 2. Architecture & Demo Flow

The demonstration follows a clear, event-driven flow:

1. **IoT Sensor Simulator**: Generates and publishes real-time turbine sensor data (temperature, vibration, acoustics) via a local Mosquitto MQTT broker.  
2. **ThingsBoard**: A separate visualization platform that also subscribes to the MQTT data stream to provide a rich, real-time dashboard of the asset's health.  
3. **Edge Simulator**: Represents an edge device that subscribes to the MQTT data, detects gross anomalies based on pre-defined thresholds, and sends a trigger to the central AI.  
4. **PCAI Agent Application**: A Flask server that receives the trigger, uses Retrieval Augmented Generation (RAG) with a local LLM to perform a detailed diagnosis, and logs its findings.  
5. **ServiceNow**: If the AI's confidence is high, the PCAI agent makes a live API call to a ServiceNow instance to automatically create a prioritized incident ticket.

## 3. Local Deployment Guide

### 3.1. Prerequisites

- Python 3.12+  
- Docker and Docker Compose  
- Ollama (LLM server)  
- LLM model (e.g., `llama3:8b`) via:

```bash
ollama pull llama3:8b
```

### 3.2. Step 1: Initial Setup

```bash
git clone <repo-url>
cd project-directory
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `config/mosquitto.conf`:

```
listener 1883
allow_anonymous true
```

Create a `docker-compose.yml` file:

```yaml
services:
  postgres:
    restart: always
    image: "postgres:16"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: thingsboard
      POSTGRES_PASSWORD: postgres

  thingsboard-ce:
    restart: always
    image: "thingsboard/tb-node:4.0.1.1"
    ports:
      - "8080:8080"
      - "1884:1883"
    depends_on:
      - postgres

volumes:
  postgres-data:
    name: tb-ce-postgres-data
```

### 3.3. Step 2: Update Configurations

- `config/demo_config.yaml`:
  - `mqtt.broker_port`: 1883
  - `thingsboard.port`: 1884
  - `thingsboard.device_access_token`: Paste after first login

### 3.4. Step 3: Launch Services

**Terminal A** – Start MQTT broker:

```bash
docker run -it --rm -p 1883:1883 -v $(pwd)/config/mosquitto.conf:/mosquitto/config/mosquitto.conf eclipse-mosquitto
```

**Terminal B** – Start ThingsBoard:

```bash
docker compose run --rm -e INSTALL_TB=true -e LOAD_DEMO=true thingsboard-ce
docker compose up
```

**Terminal C/D/E** – Set environment variables and run:

```bash
source venv/bin/activate
export SERVICENOW_API_USER="your_sn_user"
export SERVICENOW_API_PASSWORD="your_sn_password"
export OPSRAMP_TENANT_ID="your_opsramp_tenant_id"
export OPSRAMP_API_KEY="your_opsramp_api_key"
export OPSRAMP_API_SECRET="your_opsramp_api_secret"

# PCAI App
python3 -m pcai_app.main_agent

# Edge Simulator
python3 -m edge_logic.aruba_edge_simulator

# IoT Sensor
python3 -m data_simulators.iot_sensor_simulator
```

## 4. Kubernetes Deployment Guide

### 4.1. Prerequisites

- `kubectl` and access to a cluster  
- Ingress controller  
- Docker Hub or equivalent registry  

### 4.2. Step 1: Build & Push Images

```bash
export REGISTRY_PATH="your-registry"

docker build -f Dockerfile -t ${REGISTRY_PATH}/pcai-app:latest .
docker push ${REGISTRY_PATH}/pcai-app:latest

docker build -f Dockerfile.edge -t ${REGISTRY_PATH}/edge-simulator-app:latest .
docker push ${REGISTRY_PATH}/edge-simulator-app:latest

docker build -f Dockerfile.edge -t ${REGISTRY_PATH}/iot-sensor-app:latest .
docker push ${REGISTRY_PATH}/iot-sensor-app:latest
```

### 4.3. Step 2: Update Kubernetes Manifests

- Update ConfigMap and ingress hostnames in `kubernetes/base/`
- Ensure correct image URLs in all deployment manifests

### 4.4. Step 3: Create Secrets

```bash
kubectl apply -f kubernetes/base/namespace.yaml

kubectl create secret generic pcai-app-credentials   --from-literal=SERVICENOW_API_USER='your_sn_user'   --from-literal=SERVICENOW_API_PASSWORD='your_sn_password'   -n pred-maint-demo

kubectl create secret generic opsramp-credentials   --from-literal=OPSRAMP_TENANT_ID='your_opsramp_tenant_id'   --from-literal=OPSRAMP_API_KEY='your_opsramp_api_key'   --from-literal=OPSRAMP_API_SECRET='your_opsramp_api_secret'   -n pred-maint-demo
```

### 4.5. Step 4: Deploy and Access UI

**First-Time Setup:**

```bash
kubectl apply -k kubernetes/overlays/init
```

**Access UI:**

```bash
kubectl port-forward svc/thingsboard-service 8080:8080 -n pred-maint-demo
# OR use ingress
```

**Paste access token into config map**, then:

```bash
kubectl apply -k kubernetes/base/
```

## 5. Monitoring & Cleanup

```bash
kubectl get pods -n pred-maint-demo -w
kubectl logs -f deployment/iot-sensor -n pred-maint-demo
kubectl logs -f deployment/edge-simulator -n pred-maint-demo
kubectl logs -f deployment/pcai-app -n pred-maint-demo
```

**Cleanup:**

```bash
kubectl delete -k kubernetes/base/
kubectl delete secret pcai-app-credentials -n pred-maint-demo
kubectl delete secret opsramp-credentials -n pred-maint-demo
kubectl delete namespace pred-maint-demo
```

## 6. End-to-End Demo Flow

1. **Normal** – All metrics are healthy
2. **Anomaly** – Edge detects abnormality
3. **Diagnosis** – PCAI performs LLM-based analysis
4. **Remediation** – Ticket is auto-created in ServiceNow
5. **Visual Confirmation** – Dashboard updates status
