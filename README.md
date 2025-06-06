AI-Driven Predictive Maintenance Demo with HPE Technologies
1. Executive Summary
This project demonstrates an end-to-end AI-powered predictive maintenance solution for critical industrial machinery. It showcases the synergy of the HPE portfolio, including HPE Private Cloud AI (PCAI), HPE GreenLake, and OpsRamp (simulated), all underpinned by the comprehensive support of HPE Managed Services.

The core of this demonstration is an Agentic AI component, powered by a locally hosted Large Language Model (LLM), that performs advanced diagnostics. The demo directly addresses the operational and financial impact of unplanned downtime by proactively identifying potential equipment failures, performing an AI-driven diagnosis, and automatically generating a real maintenance ticket in ServiceNow. It showcases a realistic transition from reactive to proactive, intelligence-driven operations.

2. Key Capabilities & Technologies Demonstrated
Simulated Edge Logic (ArubaEdgeSimulator): Initial data processing, anomaly flagging, and actual HTTP API calls to trigger the central AI.

Central Agentic AI (PcaiAgentApplication):

Hosted in a Flask application that listens for triggers.

Utilizes a locally hosted Large Language Model (e.g., Llama 3 via Ollama) for sophisticated reasoning, diagnosis, and recommendation generation.

Employs a simple Retrieval Augmented Generation (RAG) system to provide the LLM with relevant context from local knowledge base files.

AIOps (OpsRamp - Simulated): End-to-end monitoring, event correlation, and operational dashboards are simulated through console logs, showing how a platform like OpsRamp would provide holistic visibility.

Real Workflow Automation (ServiceNow): Seamless, live API integration with a real ServiceNow Developer Instance to autonomously create and populate incident tickets with AI-generated details.

Secure Credential Management: Use of environment variables (and Kubernetes Secrets) to securely handle API credentials.

Cloud-Native Deployment: A complete guide to containerizing the application with Docker and deploying it on a Kubernetes cluster with Kustomize.

3. Folder Structure
hpe_predictive_maintenance_demo/
├── config/                   # Configuration files (e.g., demo_config.yaml)
├── data_simulators/          # Scripts for simulating IoT sensor data
├── edge_logic/               # Scripts for simulated Aruba Edge processing logic
├── knowledge_base_files/     # Text files for the RAG system
├── pcai_app/                 # Agentic AI application (Flask, LLM, RAG, Connectors)
├── utilities/                # Shared helper functions (config loading, etc.)
├── kubernetes/               # Directory for all Kubernetes manifests
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── ollama-pvc.yaml
│   │   ├── ollama-deployment.yaml
│   │   ├── ollama-service.yaml
│   │   ├── pcai-app-configmap.yaml
│   │   ├── pcai-app-deployment.yaml
│   │   ├── pcai-app-service.yaml
│   │   └── edge-simulator-deployment.yaml
│   └── overlays/
│       └── development/
│           └── kustomization.yaml
├── .gitignore
├── Dockerfile                # Dockerfile for the 'pcai_app'
├── Dockerfile.edge           # Dockerfile for the 'edge_simulator_app'
├── main_demo_runner.py       # Master script for LOCAL execution
├── README.md                 # This file
└── requirements.txt          # Python dependencies

4. Prerequisites
For Local Execution
Python: Version 3.12+ (to match the Docker environment).

Ollama: Must be installed and running locally. Ollama Website

LLM Model: A model must be pulled via Ollama (e.g., llama3:8b).

ollama pull llama3:8b

ServiceNow Developer Instance: An active Personal Developer Instance (PDI) is required. ServiceNow Developer Program

ServiceNow Credentials: You need the username and password for an API-enabled user on your ServiceNow PDI.

For Kubernetes Deployment
All prerequisites for local execution (for building/testing).

kubectl: The Kubernetes command-line tool, configured to access your cluster.

Kubernetes Cluster: A running cluster with at least one NVIDIA GPU-enabled worker node.

NVIDIA GPU Device Plugin: The NVIDIA device plugin or GPU Operator must be installed on your cluster to expose GPU resources.

Container Registry: Access to a container registry (Docker Hub, GCR, ECR, etc.) where you can push your images.

Docker: Docker (or a compatible container runtime) installed locally for building images.

5. Setup & Running the Demo (Locally)
This method uses a single script to orchestrate all components on your local machine.

Clone the Repository:

git clone <your-repository-url>
cd hpe_predictive_maintenance_demo

Create and Activate Virtual Environment:

# Use your installed python 3.12
python3.12 -m venv venv
source venv/bin/activate

Install Dependencies:

pip install -r requirements.txt

Set Up Ollama: Install Ollama and pull the required model as shown in the prerequisites. Ensure the server is running.

Set ServiceNow Environment Variables:
In your terminal, set the environment variables that the Python app will use to authenticate with ServiceNow.

On macOS/Linux:

export SERVICENOW_API_USER="your_sn_username"
export SERVICENOW_API_PASSWORD="your_sn_password"

On Windows (Command Prompt):

set SERVICENOW_API_USER="your_sn_username"
set SERVICENOW_API_PASSWORD="your_sn_password"

Configure the Demo:

Open config/demo_config.yaml.

Update pcai_app.servicenow.instance_hostname with your ServiceNow PDI hostname (e.g., dev12345.service-now.com).

Ensure pcai_app.llm_config.ollama.model_name is set to llama3:8b.

Run the Demo Runner:

python3 main_demo_runner.py

The script will launch both the PCAI app and the Edge Simulator. Press Ctrl+C to stop everything.

6. Kubernetes Deployment Guide
This guide will walk you through deploying the entire application stack to your Kubernetes cluster.

Step 1: Containerize the Applications
Build the Docker images for the pcai_app and edge_simulator_app and push them to your container registry.

# Replace 'your-registry' with your container registry path (e.g., your Docker Hub username)
export REGISTRY_PATH="your-registry"

# Build and push the PCAI application image
docker build -f Dockerfile -t ${REGISTRY_PATH}/pcai-app:latest .
docker push ${REGISTRY_PATH}/pcai-app:latest

# Build and push the Edge Simulator image
docker build -f Dockerfile.edge -t ${REGISTRY_PATH}/edge-simulator-app:latest .
docker push ${REGISTRY_PATH}/edge-simulator-app:latest

Step 2: Configure Kubernetes Manifests
You need to edit the YAML files to point to your specific resources.

Update Deployment Image Paths:

In kubernetes/base/pcai-app-deployment.yaml, change the image: line to your pcai-app image path: image: your-registry/pcai-app:latest.

In kubernetes/base/edge-simulator-deployment.yaml, change the image: line to your edge-simulator-app image path: image: your-registry/edge-simulator-app:latest.

Update ConfigMap:

In kubernetes/base/pcai-app-configmap.yaml, find the instance_hostname: key under the servicenow: section and replace the placeholder with your actual ServiceNow instance hostname.

Step 3: Deploy to Kubernetes
Execute these commands from your project's root directory.

Create the Namespace:

kubectl apply -f kubernetes/base/namespace.yaml

Create the ServiceNow Secret: (This only needs to be done once per cluster/namespace)

# Replace placeholders with your actual credentials
kubectl create secret generic pcai-app-credentials \
  --from-literal=SERVICENOW_API_USER='your_actual_sn_user' \
  --from-literal=SERVICENOW_API_PASSWORD='your_actual_sn_password' \
  -n pred-maint-demo

Apply the Application Stack using Kustomize:
This command deploys everything defined in the base directory into the pred-maint-demo namespace.

kubectl apply -k kubernetes/base/

Step 4: Verify the Deployment
Check that all your pods are up and running correctly.

# Watch the pods as they are being created (wait for STATUS to be 'Running')
kubectl get pods -n pred-maint-demo -w

# Check that the internal services have been created
kubectl get svc -n pred-maint-demo

# Check that the storage for Ollama is successfully claimed and bound
kubectl get pvc -n pred-maint-demo

You should see three running pods: ollama-..., pcai-app-..., and edge-simulator-.... If any are in an error state (ImagePullBackOff, CrashLoopBackOff), use kubectl describe pod <pod-name> -n pred-maint-demo to find the cause.

Step 5: Watch the Demo Flow & Logs
Open three separate terminals to watch the logs from each component in real-time.

Terminal 1: Edge Simulator Logs

kubectl logs -f deployment/edge-simulator -n pred-maint-demo

Terminal 2: PCAI Application Logs

kubectl logs -f deployment/pcai-app -n pred-maint-demo

Terminal 3: Ollama Server Logs

kubectl logs -f deployment/ollama -n pred-maint-demo

Watch the flow: The Edge Simulator will eventually detect an anomaly and make an HTTP call. The PCAI App log will show it received the request, queried RAG, called Ollama, and then called ServiceNow. The Ollama log will show activity when it processes the prompt.

Step 6: Cleanup
When you are finished with the demo, you can remove all the deployed resources.

Delete Resources with Kustomize:

kubectl delete -k kubernetes/base/

Delete the Secret:

kubectl delete secret pcai-app-credentials -n pred-maint-demo

Delete the Namespace:

kubectl delete namespace pred-maint-demo

7. End-to-End Demo Flow Outline
Phase 1: Normal Operations: Stable metrics from the Edge Simulator.

Phase 2: Anomaly Inception & Edge Intelligence: Anomaly is injected, detected by the edge, which sends a real HTTP trigger.

Phase 3: Agentic AI Activation: The PCAI app receives the trigger, performs RAG, and queries the local Ollama LLM with the context.

Phase 4: AI-Driven Insight & Remediation: The LLM provides a structured diagnosis, which the PCAI app uses to create a real, detailed incident ticket in ServiceNow.

Phase 5: Closed-Loop Confirmation: The newly created ticket is shown in the ServiceNow UI, demonstrating a complete, automated workflow.

8. Target Audience
Technical Decision Makers (CTOs, VPs of IT/Engineering)

IT/OT (Operational Technology) Managers