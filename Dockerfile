# Dockerfile for pcai_app

# Use a newer, supported version of Python
FROM python:3.12-slim

WORKDIR /app

# Copy shared utilities first
COPY ./utilities ./utilities

# Copy requirements first to leverage Docker cache
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the PCAI application code and its dependencies
COPY ./pcai_app ./pcai_app
COPY ./knowledge_base_files ./knowledge_base_files
COPY ./config/demo_config.yaml ./config/demo_config.yaml

EXPOSE 5000

ENV PYTHONUNBUFFERED=1

# The command to run when the container starts.
CMD ["python", "-m", "pcai_app.main_agent"]