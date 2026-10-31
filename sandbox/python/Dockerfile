FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==8.3.5
COPY runner.py /opt/codepilot/runner.py
USER 10001:10001
WORKDIR /workspace
