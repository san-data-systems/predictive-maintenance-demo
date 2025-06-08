
# AI-Driven Predictive Maintenance Demo with HPE Technologies

## 1. Executive Summary
This project demonstrates an end-to-end AI-powered predictive maintenance solution for critical industrial machinery. It showcases the synergy of the HPE portfolio, including simulated components representing HPE Private Cloud AI (PCAI), HPE GreenLake, and OpsRamp, all underpinned by the comprehensive support of HPE Managed Services.

The core of this demonstration is an Agentic AI component, powered by a locally hosted Large Language Model (LLM via Ollama), that performs advanced diagnostics. The demo directly addresses the operational and financial impact of unplanned downtime by proactively identifying potential equipment failures, performing an AI-driven diagnosis, and automatically generating a maintenance ticket in ServiceNow. It also visualizes the real-time health of the asset using a ThingsBoard dashboard.

## 2. Architecture & Demo Flow
The demonstration follows a clear, event-driven flow:

- **IoT Sensor Simulator**: Generates and publishes real-time turbine sensor data (temperature, vibration, acoustics) via a local Mosquitto MQTT broker.
- **ThingsBoard**: A separate visualization platform that also subscribes to the MQTT data stream to provide a rich, real-time dashboard of the asset's health.
- **Edge Simulator**: Represents an edge device that subscribes to the MQTT data, detects gross anomalies based on pre-defined thresholds, and sends a trigger to the central AI.
- **PCAI Agent Application**: A Flask server that receives the trigger, uses Retrieval Augmented Generation (RAG) with a local LLM to perform a detailed diagnosis, and logs its findings.
- **ServiceNow**: If the AI's confidence is high, the PCAI agent makes a live API call to a ServiceNow instance to automatically create a prioritized incident ticket.

## 3. Local Deployment Guide

This section provides instructions for running the entire demo on a local machine using separate terminals for each service.

### 3.1. Prerequisites
- **Python**: Version 3.12+
- **Docker and Docker Compose**: For running the supporting services.
- **Ollama**: Must be installed and running.
- **LLM Model**: A model must be pulled via Ollama (e.g., llama3:8b).
  ```bash
  ollama pull llama3:8b
  ```

### 3.2. Step 1: Initial Configuration

- **Clone Repository & Setup Environment**:
  ```bash
  git clone <your-repository-url>
  cd hpe_predictive_maintenance_demo
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```

- **Verify Mosquitto Config**: Ensure the file `config/mosquitto.conf` exists and contains the following:
  ```
  listener 1883
  allow_anonymous true
  ```

- **Verify ThingsBoard Docker Compose**: Ensure the `docker-compose.yml` file for ThingsBoard exists and maps the host port `1884` to the container's MQTT port `1883`.

- **Update Demo Config for Local Run**:
  - `mqtt.broker_port`: 1883
  - `thingsboard.host`: localhost
  - `thingsboard.port`: 1884
  - `pcai_app.llm_config.ollama.api_base_url`: http://localhost:11434

### 3.3. Step 2: Launch Services & Configure Token

**Terminal A: Start Mosquitto MQTT Broker**
```bash
docker run -it --rm -p 1883:1883 -v $(pwd)/config/mosquitto.conf:/mosquitto/config/mosquitto.conf eclipse-mosquitto
```

**Terminal B: Start ThingsBoard**
```bash
docker compose run --rm -e INSTALL_TB=true -e LOAD_DEMO=true thingsboard-ce
docker compose up
```

**First-Time ThingsBoard Device Setup**
- Navigate to `http://localhost:8080`
- Log in (`sysadmin@thingsboard.org` / `sysadmin`)
- Create a new device (e.g., DemoCorp_Turbine_007)
- Copy the access token
- Paste into `config/demo_config.yaml`

### 3.4. Step 3: Launch Python Applications

Open a new terminal for each:

```bash
# Set credentials in each terminal
export SERVICENOW_API_USER="your_sn_user"
export SERVICENOW_API_PASSWORD="your_sn_password"
export OPSRAMP_TENANT_ID="your_opsramp_tenant_id"
export OPSRAMP_API_KEY="your_opsramp_api_key"
export OPSRAMP_API_SECRET="your_opsramp_api_secret"
```

- Terminal C (PCAI App): `python3 -m pcai_app.main_agent`
- Terminal D (Edge Sim): `python3 -m edge_logic.aruba_edge_simulator`
- Terminal E (IoT Sensor): `python3 -m data_simulators.iot_sensor_simulator`

### 3.5. Step 4: Stopping and Cleaning Up (Local)

```bash
# Stop Docker containers
docker compose down
```

---

## 4. Kubernetes Deployment Guide

### 4.1. Prerequisites
- `kubectl`
- Ingress controller
- Container registry

### 4.2. Step 1: Build and Push Docker Images

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

- Update ConfigMap `pcai-app-configmap.yaml` and `thingsboard-ingress.yaml`

### 4.4. Step 3: Create Kubernetes Secrets

```bash
kubectl apply -f kubernetes/base/namespace.yaml

kubectl create secret generic pcai-app-credentials   --from-literal=SERVICENOW_API_USER='your_sn_user'   --from-literal=SERVICENOW_API_PASSWORD='your_sn_password'   -n pred-maint-demo

kubectl create secret generic opsramp-credentials   --from-literal=OPSRAMP_TENANT_ID='your_opsramp_tenant_id'   --from-literal=OPSRAMP_API_KEY='your_opsramp_api_key'   --from-literal=OPSRAMP_API_SECRET='your_opsramp_api_secret'   -n pred-maint-demo
```

### 4.5. Step 4: Deploy to Kubernetes

```bash
kubectl apply -k kubernetes/overlays/init
kubectl delete job thingsboard-init-db -n pred-maint-demo
kubectl port-forward svc/thingsboard-service 8080:8080 -n pred-maint-demo
```

Update ConfigMap with real device token and then:

```bash
kubectl apply -k kubernetes/base/
```

---

## 5. Managing the Kubernetes Deployment

### 5.1. Verify the Deployment

```bash
kubectl get pods -n pred-maint-demo -w
kubectl get svc,pvc -n pred-maint-demo
kubectl get ingress -n pred-maint-demo
```

### 5.2. Watch Logs

```bash
kubectl logs -f deployment/iot-sensor -n pred-maint-demo
kubectl logs -f deployment/edge-simulator -n pred-maint-demo
kubectl logs -f deployment/pcai-app -n pred-maint-demo
```

### 5.3. Cleanup

```bash
kubectl delete -k kubernetes/base/
kubectl delete secret pcai-app-credentials -n pred-maint-demo
kubectl delete secret opsramp-credentials -n pred-maint-demo
kubectl delete namespace pred-maint-demo
```

---

## 6. End-to-End Demo Flow Outline

- **Phase 1: Normal Operations** — All metrics green.
- **Phase 2: Anomaly Inception** — Deviation detected.
- **Phase 3: AI Diagnosis** — RAG-based evaluation.
- **Phase 4: Remediation** — Incident created in ServiceNow.
- **Phase 5: Confirmation** — Dashboard reflects maintenance status.
