# Dockerfile for pcai_app

# Use a newer, supported version of Python
FROM python:3.12-slim

WORKDIR /app

# Copy shared utilities first
COPY ./utilities ./utilities

# Copy requirements first to leverage Docker cache
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the PCAI application code
COPY ./pcai_app ./pcai_app

# IMPORTANT: Copy knowledge_base_files to a known absolute path.
# This assumes your RAGSystem is configured to look for this path.
COPY ./knowledge_base_files /app/knowledge_base_files 

# IMPORTANT: Copy demo_config.yaml to a known absolute path.
# This ensures common_utils.py can find it reliably.
COPY ./config/demo_config.yaml /app/config/demo_config.yaml 


EXPOSE 5000

ENV PYTHONUNBUFFERED=1

# The command to run when the container starts.
CMD ["python", "-m", "pcai_app.main_agent"]